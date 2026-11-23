"""campus.api.authz

Fail-closed authorization for campus.api routes, backed by circles
(docs/circles-access-control.md).

Authentication (campus.auth.middleware via the api blueprint's
before_request) establishes who is calling and pushes the principal
into flask.g; this module decides what the principal may do on the
api's domain resources. Every check fails closed: a principal that
matches no role, a missing role circle, or a missing user identity is
denied.

Model: circles contain only circles. Each guarded resource family has
a resource circle with an `<resource>.admin` role circle whose members
hold the admin role on that resource family. Members are either user
circles (named after the email account) or nested circles (group
circles). Since user circles are named after the email, the check for
a user principal is a direct members-dict lookup keyed by the caller's
user ID (the email); on a direct miss, membership resolves
transitively through the role circle's member group circles (#1196) —
a seeded group (e.g. a school-wide `student` group) confers the role
to its users without enumerating them into the role circle. The
transitive walk is resources.circle.resolve_member (#1202), the single
membership resolver shared with the probe route.

Principals:

- User principals (bearer tokens minted for an end user): authorized
  by membership in the resource's admin role circle. The role circle's
  configured access values are a reserved refinement (tiers) — today
  membership alone grants the role.
- Client principals (HTTP Basic or app-scoped client_credentials
  tokens): hold no domain authority and are denied on every gated
  route. Domain administration must be attributable to a user, the
  same rule campus.auth applies to its management blueprints (#854).

Booking authority is venue-scoped, not a flat resource family
(campus#1217): `venues.admin` members act on every venue's bookings,
and a venue whose metadata carries a `category` additionally answers
to a standalone `venues.<category-slug>.admin` role circle ("Sports
Facilities" -> `venues.sports-facilities.admin`). The scoped circles
are deliberately NOT members of `venues.admin` — nesting would confer
all-venue authority through transitive resolution (#1196) — and the
bootstrap no longer seeds a flat `bookings.admin` role circle; there
is no `require_resource_admin("bookings")`.

Enforcement lives in the route modules (the resources must stay
ungated for in-process callers, such as test fixtures and the other
services sharing this deployment shape).

Boundary (ratified 2026-11-06): the access-grant store is campus.auth's
management authority and is never consulted here — resource-scoped
grant vocabularies (e.g. `timetable:*`) confer no campus.api authority.
See docs/circles-access-control.md.
"""

__all__ = [
    "require_resource_admin",
    "require_user_principal",
    "require_venue_authority",
    "has_venue_authority",
]

import re

import flask

from campus.common import schema
from campus.common.errors import api_errors

from .resources import venue as venue_resource
from .resources.circle import circle_storage, resolve_member


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


def _admin_role_circle(role_name: str) -> dict | None:
    """The named role circle record, or None if absent.

    Circle names are unique (best-effort), so the role circle is
    resolved by name — the stable key across UID format changes.
    Callers pass the full circle name ("timetable.admin",
    "venues.sports-facilities.admin").
    """
    matches = circle_storage.get_matching({"name": role_name})
    if not matches:
        return None
    return matches[0]


def require_resource_admin(
        resource: str,
        action_label: str | None = None,
) -> None:
    """Require membership in the `<resource>.admin` role circle.

    The domain gate for campus.api mutation routes: the caller must be
    a user principal whose user ID (email, = their user circle's name)
    appears in the role circle's members dict, or is a member of a
    circle reachable through the role circle's member group circles
    (#1196). Everything else is denied.

    Args:
        resource: The API resource family, matching its bootstrap
            circle name ("circles", "timetable", "assignments",
            "bookings", "submissions").
        action_label: Optional verb phrase for the denial message
            (e.g. "create bookings"), interpolated as
            "... may {action_label}". Labels never gate: omitting one
            only degrades the message to "perform this action".

    Raises:
        api_errors.ForbiddenError: If the caller lacks the role.
    """
    action = action_label or "perform this action"
    user_id = _principal_user_id()
    if user_id is None:
        raise api_errors.ForbiddenError(
            f"Client principals may not {action} on the '{resource}' "
            "resource: domain administration must be attributable to "
            "a user (#854)"
        )
    role_circle = _admin_role_circle(f"{resource}.admin")
    if role_circle is None:
        raise api_errors.ForbiddenError(
            f"No '{resource}.admin' role circle is configured: "
            f"denying '{action}' fail-closed — run the circles "
            "bootstrap (docs/circles-access-control.md)"
        )
    members = role_circle.get("members", {})
    # The direct dict hit stays as the cheap fast path (#1202): direct
    # membership trivially implies transitive membership, so the
    # decision is identical either way. On a direct miss, resolution
    # goes through the shared resolver — the same implementation the
    # membership probe answers through, so gate and probe cannot drift.
    if user_id not in members and not resolve_member(
            schema.CampusID(role_circle[schema.CAMPUS_KEY]),
            schema.CampusID(user_id),
    ):
        raise api_errors.ForbiddenError(
            f"Only members of the '{resource}.admin' circle may "
            f"{action} on the '{resource}' resource"
        )

def require_user_principal(action_label: str | None = None) -> str:
    """Require a user principal and return its ID (the email).

    Client principals (no user) are denied: the action must be
    attributable to a user (#854). Routes that attribute a record to
    its creator rather than to a role — booking creation — call this
    instead of a role gate.
    """
    action = action_label or "perform this action"
    user_id = _principal_user_id()
    if user_id is None:
        raise api_errors.ForbiddenError(
            f"Client principals may not {action}: domain "
            "administration must be attributable to a user (#854)"
        )
    return user_id


def category_slug(category: str) -> str:
    """Slug a venue category into the scoped-circle name fragment.

    The contract backing `venues.<category-slug>.admin` resolution:
    lowercase, collapse every non-alphanumeric run to a single
    hyphen, strip the ends — "Sports Facilities" becomes
    "sports-facilities".
    """
    return re.sub(r"[^a-z0-9]+", "-", category.strip().lower()).strip("-")


def _is_role_member(role_name: str, user_id: str) -> bool:
    """True if user_id holds the named role circle, transitively.

    A missing circle is simply not a membership (callers that need to
    distinguish it for the denial message do their own lookup). The
    direct hit stays as the fast path, with the shared resolver
    behind it (#1202) — the same decision require_resource_admin
    makes for flat resource families.
    """
    role_circle = _admin_role_circle(role_name)
    if role_circle is None:
        return False
    members = role_circle.get("members", {})
    if user_id in members:
        return True
    return bool(resolve_member(
        schema.CampusID(role_circle[schema.CAMPUS_KEY]),
        schema.CampusID(user_id),
    ))


def _venue_authority_denial(
        venue_id: schema.CampusID,
        user_id: str,
        action: str,
) -> str | None:
    """Why the user lacks booking authority on the venue, or None.

    `venues.admin` is the global authority (campus#1217's ratified
    bundling of bookings into venues). A venue whose metadata carries
    a `category` additionally answers to the standalone
    `venues.<category-slug>.admin` circle; uncategorized venues are
    venues.admin-only, and a missing scoped circle denies fail-closed
    rather than silently widening to nobody-or-global.
    """
    if _is_role_member("venues.admin", user_id):
        return None
    venue = venue_resource.get(venue_id)  # unknown venue -> 404
    category = venue.metadata.get("category")
    if not isinstance(category, str) or not category.strip():
        return (
            f"Venue {venue_id} has no \"category\" in its metadata: "
            f"only venues.admin members may {action} its bookings"
        )
    role_name = f"venues.{category_slug(category)}.admin"
    if _admin_role_circle(role_name) is None:
        return (
            f"No '{role_name}' circle is configured for venue "
            f"{venue_id}'s \"{category}\" category: denying "
            "fail-closed — create the circle to delegate booking "
            "authority for the category"
        )
    if not _is_role_member(role_name, user_id):
        return (
            f"Only members of 'venues.admin' or '{role_name}' may "
            f"{action} bookings for venue {venue_id}"
        )
    return None


def require_venue_authority(
        venue_id: schema.CampusID,
        action_label: str | None = None,
) -> None:
    """Require booking authority on the venue (campus#1217).

    The domain gate for booking decisions: the caller must be a user
    principal holding `venues.admin` (any venue) or membership in the
    standalone `venues.<category-slug>.admin` circle for the venue's
    metadata category. Unknown venues surface as 404 via the venue
    lookup; everything else fails closed with the specific reason.

    Raises:
        api_errors.ForbiddenError: If the caller lacks authority.
        api_errors.NotFoundError: If the venue does not exist.
    """
    action = action_label or "perform this action"
    user_id = require_user_principal(action)
    denial = _venue_authority_denial(venue_id, user_id, action)
    if denial is not None:
        raise api_errors.ForbiddenError(denial)


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
        return _venue_authority_denial(venue_id, user_id, "act on") is None
    except api_errors.NotFoundError:
        return False
