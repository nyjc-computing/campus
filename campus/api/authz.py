"""campus.api.authz

Fail-closed authorization for campus.api routes, backed by circles
(docs/circles-access-control.md — the ratified access model,
campus#1216).

Authentication (campus.auth.middleware via the api blueprint's
before_request) establishes who is calling and pushes the principal
into flask.g; this module decides what the principal may do on the
api's domain resources. Every check fails closed: a principal that
holds no applicable value, a missing grant circle, or a missing user
identity is denied.

Model (ratified 2026-11-23): authority is the access value on
membership edges, encoded as 8-bit dual-scope constants
(`0 | G-c G-m G-r | S-c S-m S-r | 0`) — group-scope and self-scope
permission sets per family. Three sources combine per the resolution
algorithm:

- the `campus` wildcard: a campus:admin membership confers admin on
  every family (the one cross-family authority, checked first);
- the baseline: a principal's primary-group membership value
  (`staff:viewer`, `student:guest`) is their platform-wide floor;
- family-directed edges: values on edges into the family's grant
  circle, reached directly (user circles) or through member-list
  circles (committees, venue-category subcircles). Category
  subcircles narrow group-scope authority (a sports booking resolves
  through `venues.sports-facilities`, not through family-level
  edges); self-scope authority is never narrowed.

Resolution answers through the shared membership resolver
(resources.circle.resolve_member / resolve_family_access) — the same
implementation the probe route answers through, so gate and probe
cannot drift.

Principals:

- User principals (bearer tokens minted for an end user) resolve as
  above.
- Client principals (HTTP Basic or app-scoped client_credentials
  tokens) hold no domain authority and are denied on every gated
  route. Domain administration must be attributable to a user, the
  same rule campus.auth applies to its management blueprints (#854).

Booking authority is venue-derived, not a flat resource family
(campus#1217/#1218): a booking decision is a group-scope modify on
the `venues` family, category-narrowed by the booking venue's
metadata category; creating and managing one's own bookings is a
self-scope check on the same family. There is no
`require_resource_admin("bookings")`.

Enforcement lives in the route modules (the resources must stay
ungated for in-process callers, such as test fixtures and the other
services sharing this deployment shape).

Boundary (ratified 2026-11-06): the access-grant store is campus.auth's
management authority and is never consulted here — resource-scoped
grant vocabularies (e.g. `timetable:*`) confer no campus.api authority.
See docs/circles-access-control.md.
"""

__all__ = [
    "ACCESS_ADMIN",
    "ACCESS_EDITOR",
    "ACCESS_VIEWER",
    "ACCESS_SELF",
    "ACCESS_GUEST",
    "ACCESS_CONSTANTS",
    "has_permission",
    "validate_access_constant",
    "require_resource_access",
    "require_resource_admin",
    "require_user_principal",
    "require_venue_authority",
    "has_venue_authority",
    "category_slug",
]

import re

import flask

from campus.common import schema
from campus.common.errors import api_errors

from .resources import venue as venue_resource
from .resources.circle import (
    ACCESS_ADMIN,
    ACCESS_CONSTANTS,
    ACCESS_EDITOR,
    ACCESS_GUEST,
    ACCESS_SELF,
    ACCESS_VIEWER,
    CAMPUS_CIRCLE_NAME,
    GROUP_FIELD_MASK,
    SELF_FIELD_MASK,
    circle_storage,
    has_permission,
    resolve_family_access,
    resolve_member,
    validate_access_constant,
)

# Family × operation table (docs/circles-access-control.md): which
# (scope, permission) checks each family honors. A check a family does
# not honor denies regardless of the resolved value — self-scope
# authority on a family with no own-semantics is vacuous, and the
# table is where that ruling lives.
FAMILY_OPERATIONS: dict[str, dict[str, set[str]]] = {
    "timetable": {
        "group": {"create", "modify", "read"},
        "self": {"read"},
    },
    "subjcombi": {
        "group": {"create", "modify", "read"},
        "self": {"read"},
    },
    # The users directory (#1226): read-only by construction — the
    # family honors no write semantics, so identity mutation stays
    # walled in campus.auth's management surface. Group read serves
    # the /users facade's full-list lane (staff:viewer baseline);
    # self read lets any authenticated user fetch their own record
    # (student:guest carries S-r). Student group-read is granted by
    # no baseline: their visibility is the facade's query rewrite
    # over circles they can read.
    "users": {
        "group": {"read"},
        "self": {"read"},
    },
    "venues": {
        "group": {"create", "modify", "read"},
        "self": {"create", "modify", "read"},
    },
    "files": {
        "group": {"create", "modify", "read"},
        "self": {"create", "modify", "read"},
    },
    "assignments": {"group": {"create", "modify", "read"}},
    "submissions": {"group": {"create", "modify", "read"}},
    "circles": {"group": {"create", "modify", "read"}},
    "hostedapps": {"group": {"create", "modify", "read"}},
}


def _principal_user_id() -> str | None:
    """The authenticated user's ID, if the principal is a user.

    The campus_python SDK hydrates the authenticate result's user into
    a campus.model.User object; some test doubles carry a plain dict —
    handle both. Client principals have no user at all.
    """
    user = getattr(flask.g, "current_user", None)
    value = (
        user.get("id") if isinstance(user, dict)
        else getattr(user, "id", None)
    )
    return str(value) if value else None


def require_user_principal(action_label: str | None = None) -> str:
    """Require a user principal and return its ID (the email).

    Client principals (no user) are denied: the action must be
    attributable to a user (#854). Routes that attribute a record to
    its creator rather than to a role — booking creation — call this
    alongside a scope gate.
    """
    action = action_label or "perform this action"
    user_id = _principal_user_id()
    if user_id is None:
        raise api_errors.ForbiddenError(
            f"Client principals may not {action}: domain "
            "administration must be attributable to a user (#854)"
        )
    return user_id


def is_platform_admin(user_id: str) -> bool:
    """True if the user holds the `campus` wildcard at admin.

    A campus:admin membership confers admin on every resource family;
    checked before any family resolution. The resolved value must
    carry the group-create bit — membership at a lesser constant does
    not wildcard.
    """
    try:
        matches = circle_storage.get_matching({"name": CAMPUS_CIRCLE_NAME})
    except Exception:
        return False
    if not matches:
        return False
    resolution = resolve_member(
        schema.CampusID(matches[0][schema.CAMPUS_KEY]),
        schema.CampusID(user_id),
    )
    if resolution is None:
        return False
    return has_permission(resolution["access_value"], "group", "create")


def _effective(
        resource: str,
        user_id: str,
        category: str | None = None,
) -> dict | None:
    """The principal's effective access on a family, or None.

    None means fail-closed: no grant circle for the family. The
    wildcard short-circuits to full admin on both scopes; otherwise
    resolution goes through resolve_family_access (baseline + family
    edges + category narrowing of the group field).
    """
    if is_platform_admin(user_id):
        return {
            "g": GROUP_FIELD_MASK,
            "s": SELF_FIELD_MASK,
            "narrowed": False,
            "wildcard": True,
        }
    return resolve_family_access(
        resource,
        schema.CampusID(user_id),
        narrow_to_label=category_slug(category) if category else None,
    )


def require_resource_access(
        resource: str,
        scope: str,
        permission: str,
        action_label: str | None = None,
        category: str | None = None,
) -> None:
    """Require an effective permission bit on a resource family.

    The domain gate for campus.api routes. The caller must be a user
    principal whose effective access on the family — baseline, family
    edges, category narrowing, `campus` wildcard — carries the
    permission bit in the requested scope, and the family's operation
    table must honor the (scope, permission) check.

    Args:
        resource: The API resource family, matching its grant circle
            name ("circles", "timetable", "venues", ...).
        scope: "group" (family's shared resources) or "self" (the
            caller's own resources within the family).
        permission: "create", "modify", or "read".
        action_label: Optional verb phrase for the denial message
            (e.g. "create bookings"); labels never gate.
        category: Optional venue category for category-narrowed
            families (booking ops on `venues`): when the caller holds
            the matching category subcircle, its edge is the sole
            source of group-scope authority.

    Raises:
        api_errors.ForbiddenError: If the caller lacks the permission.
    """
    action = action_label or "perform this action"
    user_id = require_user_principal(action)
    honored = FAMILY_OPERATIONS.get(resource, {}).get(scope, set())
    if permission not in honored:
        raise api_errors.ForbiddenError(
            f"The '{resource}' family does not honor {scope}-scope "
            f"{permission} operations"
        )
    effective = _effective(resource, user_id, category)
    if effective is None:
        raise api_errors.ForbiddenError(
            f"No '{resource}' grant circle is configured: denying "
            f"'{action}' fail-closed — run the circles bootstrap "
            "(docs/circles-access-control.md)"
        )
    field = effective["g"] if scope == "group" else effective["s"]
    if not has_permission(field, scope, permission):
        raise api_errors.ForbiddenError(
            _denial_message(resource, scope, permission, action, effective)
        )


def _denial_message(
        resource: str,
        scope: str,
        permission: str,
        action: str,
        effective: dict,
) -> str:
    """Shape the 403 message with the resolution's provenance."""
    detail = "baseline and family edges"
    if effective.get("wildcard"):
        detail = "the campus wildcard"  # unreachable: wildcard passes
    elif effective.get("narrowed"):
        detail = "the category subcircle edge (narrowest path)"
    return (
        f"Effective access on '{resource}' ({detail}) does not carry "
        f"{scope}-scope {permission}: may not {action} "
        f"(resolved group=0b{effective['g']:07b}, "
        f"self=0b{effective['s']:07b})"
    )


def require_resource_admin(
        resource: str,
        action_label: str | None = None,
) -> None:
    """Require group-scope create authority on a resource family.

    The CRUD gate: family-resource create (and, by the c⇒delete
    convention, delete) plus every lesser group power. Kept as the
    legacy call-site spelling — timetable/venue/subjcombi/... mutation
    routes express their gate through it; the decision is
    require_resource_access(resource, "group", "create").
    """
    require_resource_access(resource, "group", "create", action_label)


def category_slug(category: str) -> str:
    """Slug a venue category into the scoped-circle label fragment.

    The contract backing `venues.<category-slug>` subcircle matching:
    lowercase, collapse every non-alphanumeric run to a single
    hyphen, strip the ends — "Sports Facilities" becomes
    "sports-facilities".
    """
    return re.sub(r"[^a-z0-9]+", "-", category.strip().lower()).strip("-")


def _venue_category(venue_id: schema.CampusID) -> str | None:
    """Load the venue and return its metadata category, or None.

    Raises:
        api_errors.NotFoundError: If the venue does not exist.
    """
    venue = venue_resource.get(venue_id)  # unknown venue -> 404
    category = venue.metadata.get("category")
    if not isinstance(category, str) or not category.strip():
        return None
    return category


def require_venue_authority(
        venue_id: schema.CampusID,
        action_label: str | None = None,
) -> None:
    """Require booking authority on the venue (campus#1217/#1218).

    The domain gate for booking decisions: a group-scope modify on
    the `venues` family, category-narrowed — a caller holding the
    venue's category subcircle resolves authority through that edge
    exclusively; otherwise family-level edges and the baseline apply,
    and the `campus` wildcard passes everywhere. Uncategorized venues
    resolve at family level (whoever holds group authority on venues
    decides their bookings). Unknown venues surface as 404 via the
    venue lookup; everything else fails closed with the specific
    reason.

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
        api_errors.NotFoundError: If the venue does not exist.
    """
    action = action_label or "perform this action"
    require_user_principal(action)
    category = _venue_category(venue_id)
    require_resource_access(
        "venues",
        "group",
        "modify",
        action_label=action,
        category=category,
    )


def has_venue_authority(venue_id: schema.CampusID) -> bool:
    """Non-raising venue-authority check for owner-or-authority rules.

    Same decision `require_venue_authority` makes; an unknown venue
    is not authority. Routes use it where the caller's own record
    (e.g. their pending booking) already grants the action and the
    gate only widens it.
    """
    user_id = _principal_user_id()
    if user_id is None:
        return False
    try:
        category = _venue_category(venue_id)
    except api_errors.NotFoundError:
        return False
    if "modify" not in FAMILY_OPERATIONS["venues"]["group"]:
        return False
    effective = _effective("venues", user_id, category)
    if effective is None:
        return False
    return has_permission(effective["g"], "group", "modify")
