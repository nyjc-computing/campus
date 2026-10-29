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
(user circles, named after the email account) hold the admin role on
that resource family. Since user circles are named after the email,
the check for a user principal is a direct members-dict lookup keyed
by the caller's user ID (the email).

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
"""

__all__ = [
    "require_resource_admin",
]

import flask

from campus.common.errors import api_errors

from .resources.circle import circle_storage


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


def _admin_role_members(resource: str) -> dict | None:
    """The members dict of `<resource>.admin`, or None if absent.

    Circle names are unique (best-effort), so the role circle is
    resolved by name — the stable key across UID format changes.
    """
    matches = circle_storage.get_matching({"name": f"{resource}.admin"})
    if not matches:
        return None
    return matches[0].get("members", {})


def require_resource_admin(
        resource: str,
        action_label: str | None = None,
) -> None:
    """Require membership in the `<resource>.admin` role circle.

    The domain gate for campus.api mutation routes: the caller must be
    a user principal whose user ID (email, = their user circle's name)
    appears in the role circle's members dict. Everything else is
    denied.

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
    members = _admin_role_members(resource)
    if members is None:
        raise api_errors.ForbiddenError(
            f"No '{resource}.admin' role circle is configured: "
            f"denying '{action}' fail-closed — run the circles "
            "bootstrap (docs/circles-access-control.md)"
        )
    if user_id not in members:
        raise api_errors.ForbiddenError(
            f"Only members of the '{resource}.admin' circle may "
            f"{action} on the '{resource}' resource"
        )
