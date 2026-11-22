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
]

import flask

from campus.common import schema
from campus.common.errors import api_errors

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


def _admin_role_circle(resource: str) -> dict | None:
    """The `<resource>.admin` role circle record, or None if absent.

    Circle names are unique (best-effort), so the role circle is
    resolved by name — the stable key across UID format changes.
    """
    matches = circle_storage.get_matching({"name": f"{resource}.admin"})
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
    role_circle = _admin_role_circle(resource)
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
