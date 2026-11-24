"""campus.auth.integration_actions.routes

HTTP surface for integration action proxies (#1221): allowlisted,
admin-authorized verbs that campus.auth performs on a TARGET user's
stored integration credential. The provider's tokens never leave the
process — responses carry action outcomes only.

POST /auth/v1/integrations/{base_provider}/{integration}/users/{user_id}/turn-in
    {course_id, coursework_id[, submission_id]}
POST /auth/v1/integrations/.../users/{user_id}/reclaim             (same body)
POST /auth/v1/integrations/.../users/{user_id}/modify-attachments
    {course_id, coursework_id, submission_id, attachments: [{link: {url}}]}
GET  /auth/v1/integrations/.../users/{user_id}/submission
    ?course_id=&coursework_id=[&submission_id=]

All verbs gate through `authz.require_integration_action` (capability
scope + vault custody authority), load the released credential
in-process, and emit `campus.integrations.action` / `.action_fail`
audit events naming the actor, the target user, and the ids — never
token material.
"""

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.errors import base as error_base

from .. import authz, get_yapper, integrations
from . import classroom
from .credentials import load_released_credential

bp = flask.Blueprint(
    'integration_actions', __name__, url_prefix='/integrations')

# Classroom scopes the allowlisted verbs run under (consent-bounded:
# the target user's stored grant must cover them, campus#1095).
_COURSEWORK_ME = "https://www.googleapis.com/auth/classroom.coursework.me"

# provider -> {action -> required upstream scopes}. The allowlist is
# deliberately explicit: a new integration or verb opts in here, and
# anything unlisted answers 404 (no path passthrough).
_ACTION_SCOPES: dict[str, dict[str, tuple[str, ...]]] = {
    "google.classroom": {
        "turn-in": (_COURSEWORK_ME,),
        "reclaim": (_COURSEWORK_ME,),
        "modify-attachments": (_COURSEWORK_ME,),
        "get-submission": (_COURSEWORK_ME,),
    },
}

_STATE_TURNED_IN = "TURNED_IN"


def _actor() -> dict:
    """Who is driving the proxy (audit attribution; #881)."""
    user = flask.g.current_user
    if user:
        return {"actor_type": "user", "actor_id": str(user.get("id"))}
    client = flask.g.current_client
    return {
        "actor_type": "client",
        "actor_id": str(client.id) if client else None,
    }


def _emit(event: str, actor: dict, **details) -> None:
    get_yapper().emit(event, {**actor, **details})


def _resolve_action(
        base_provider: str, integration: str, action: str,
) -> tuple[integrations.Integration, tuple[str, ...]]:
    """The registered integration + the action's required scopes.

    404 fail-closed on unknown slug, base-provider mismatch, or an
    integration/verb pair outside the allowlist (no path passthrough).
    """
    provider_str = f"{base_provider}.{integration}"
    campus_integration = integrations.resolve(provider_str)
    required_scopes = _ACTION_SCOPES.get(provider_str, {}).get(action)
    if required_scopes is None:
        raise api_errors.NotFoundError(
            f"No allowlisted '{action}' action for integration "
            f"{provider_str!r} (#1221)",
            provider=provider_str,
            action=action,
        )
    return campus_integration, required_scopes


def _run(
        base_provider: str,
        integration: str,
        user_id: str,
        action: str,
        *,
        run,
) -> flask_campus.JsonResponse:
    """Shared action flow: gate -> released credential -> verb -> audit.

    `run(access_token)` performs the upstream calls and returns the
    response payload. Google-side failures emit `.action_fail` (actor,
    target, ids — never tokens) before propagating as typed errors.
    """
    campus_integration, required_scopes = _resolve_action(
        base_provider, integration, action)
    authz.require_integration_action(campus_integration.provider, action)
    actor = _actor()
    target_id = schema.UserID(user_id)
    try:
        # The loader's denials (no credential, grant missing the
        # scopes) are audited like Google-side failures: an attempt to
        # act is security-relevant whoever blocked it.
        access_token, _scope = load_released_credential(
            campus_integration, target_id, list(required_scopes),
        )
        result = run(access_token=access_token)
    except (api_errors.APIError, error_base.OAuthError) as err:
        _emit(
            "campus.integrations.action_fail",
            actor,
            user_id=str(target_id),
            provider=campus_integration.provider,
            integration=campus_integration.slug,
            action=action,
            error=type(err).__name__,
        )
        raise
    _emit(
        "campus.integrations.action",
        actor,
        user_id=str(target_id),
        provider=campus_integration.provider,
        integration=campus_integration.slug,
        action=action,
    )
    return result, 200


def _resolve_submission_id(
        course_id: str,
        coursework_id: str,
        submission_id: str,
        *,
        access_token: str,
) -> str:
    """The target user's studentSubmission id on the CourseWork.

    With no explicit id, resolved via list(userId=me) — the released
    credential belongs to the target user.
    """
    if submission_id:
        return submission_id
    submissions = classroom.list_student_submissions(
        course_id, coursework_id, access_token=access_token)
    if not submissions:
        raise api_errors.NotFoundError(
            "No studentSubmission for the target user on this CourseWork"
        )
    return submissions[0]["id"]


@bp.post(
    "/<base_provider>/<integration>/users/<user_id>/turn-in",
    endpoint="turn_in",
)
@flask_campus.unpack_request
def turn_in(
        base_provider: str,
        integration: str,
        user_id: str,
        course_id: str,
        coursework_id: str,
        submission_id: str = "",
        **_extra,
) -> flask_campus.JsonResponse:
    """Turn the target user's submission in on a CourseWork (#1221).

    No-op success when the submission is already TURNED_IN (the
    Classroom-native re-submit semantics). Requires the
    `integrations.<provider>:admin` scope AND vault access to the
    integration's label.
    """
    def run(*, access_token: str) -> dict:
        resolved_id = _resolve_submission_id(
            course_id, coursework_id, submission_id,
            access_token=access_token,
        )
        submission = classroom.get_student_submission(
            course_id, coursework_id, resolved_id,
            access_token=access_token,
        )
        if submission.get("state") == _STATE_TURNED_IN:
            return {
                "action": "turn-in",
                "course_id": course_id,
                "coursework_id": coursework_id,
                "submission_id": resolved_id,
                "state": _STATE_TURNED_IN,
                "turned_in": False,
                "already": True,
            }
        classroom.turn_in(
            course_id, coursework_id, resolved_id,
            access_token=access_token,
        )
        return {
            "action": "turn-in",
            "course_id": course_id,
            "coursework_id": coursework_id,
            "submission_id": resolved_id,
            "state": _STATE_TURNED_IN,
            "turned_in": True,
            "already": False,
        }

    return _run(base_provider, integration, user_id, "turn-in", run=run)


@bp.post(
    "/<base_provider>/<integration>/users/<user_id>/reclaim",
    endpoint="reclaim",
)
@flask_campus.unpack_request
def reclaim(
        base_provider: str,
        integration: str,
        user_id: str,
        course_id: str,
        coursework_id: str,
        submission_id: str = "",
        **_extra,
) -> flask_campus.JsonResponse:
    """Reclaim the target user's turned-in submission (#1221).

    A Google FAILED_PRECONDITION means there is nothing to reclaim
    (state NEW or already reclaimed) and counts as success — the
    Classroom-native semantics the submit mirror relies on.
    """
    def run(*, access_token: str) -> dict:
        resolved_id = _resolve_submission_id(
            course_id, coursework_id, submission_id,
            access_token=access_token,
        )
        try:
            classroom.reclaim(
                course_id, coursework_id, resolved_id,
                access_token=access_token,
            )
        except api_errors.InvalidRequestError as err:
            if getattr(err, "details", None) and err.details.get(
                    "google_status") == classroom.FAILED_PRECONDITION:
                return {
                    "action": "reclaim",
                    "course_id": course_id,
                    "coursework_id": coursework_id,
                    "submission_id": resolved_id,
                    "reclaimed": False,
                    "already": True,
                }
            raise
        return {
            "action": "reclaim",
            "course_id": course_id,
            "coursework_id": coursework_id,
            "submission_id": resolved_id,
            "reclaimed": True,
        }

    return _run(base_provider, integration, user_id, "reclaim", run=run)


@bp.post(
    "/<base_provider>/<integration>/users/<user_id>/modify-attachments",
    endpoint="modify_attachments",
)
@flask_campus.unpack_request
def modify_attachments(
        base_provider: str,
        integration: str,
        user_id: str,
        course_id: str,
        coursework_id: str,
        submission_id: str,
        attachments: list[dict],
        **_extra,
) -> flask_campus.JsonResponse:
    """Add link attachments to the target user's submission (#1221).

    `attachments` items are Google's addAttachments shape, e.g.
    {"link": {"url": "https://..."}}; Classroom fetches titles itself.
    """
    if not attachments or not all(
            isinstance(item, dict) and (item.get("link") or {}).get("url")
            for item in attachments
    ):
        raise api_errors.InvalidRequestError(
            "attachments must be a non-empty list of "
            '{"link": {"url": "..."}} items',
        )

    def run(*, access_token: str) -> dict:
        classroom.modify_attachments(
            course_id, coursework_id, submission_id, attachments,
            access_token=access_token,
        )
        return {
            "action": "modify-attachments",
            "course_id": course_id,
            "coursework_id": coursework_id,
            "submission_id": submission_id,
            "attached": len(attachments),
        }

    return _run(
        base_provider, integration, user_id, "modify-attachments", run=run,
    )


@bp.get(
    "/<base_provider>/<integration>/users/<user_id>/submission",
    endpoint="get_submission",
)
@flask_campus.unpack_request
def get_submission(
        base_provider: str,
        integration: str,
        user_id: str,
        course_id: str,
        coursework_id: str,
        submission_id: str = "",
        **_extra,
) -> flask_campus.JsonResponse:
    """Read the target user's submission state + attachments (#1221).

    Metadata only — the Classroom resource carries no token material.
    """
    def run(*, access_token: str) -> dict:
        resolved_id = _resolve_submission_id(
            course_id, coursework_id, submission_id,
            access_token=access_token,
        )
        return classroom.get_student_submission(
            course_id, coursework_id, resolved_id,
            access_token=access_token,
        )

    return _run(base_provider, integration, user_id, "get-submission", run=run)


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation."""
    new_bp = flask.Blueprint(
        'integration_actions', __name__, url_prefix='/integrations')
    prefix = "/<base_provider>/<integration>/users/<user_id>"
    new_bp.add_url_rule(
        f"{prefix}/turn-in", "turn_in", turn_in, methods=["POST"])
    new_bp.add_url_rule(
        f"{prefix}/reclaim", "reclaim", reclaim, methods=["POST"])
    new_bp.add_url_rule(
        f"{prefix}/modify-attachments", "modify_attachments",
        modify_attachments, methods=["POST"])
    new_bp.add_url_rule(
        f"{prefix}/submission", "get_submission", get_submission,
        methods=["GET"])
    return new_bp
