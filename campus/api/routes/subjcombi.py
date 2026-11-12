"""campus.api.routes.subjcombi

API routes for the Subjcombi resource: the maintained mapping of a
user to a timetable lessongroup (#592).

Changes append effective-dated records — the records are the mutation
trail — and scheduled changes take effect as a read-time fact at their
`effective_from` (date-only values default to 07:00 school time), so
no scheduler process exists. Mutations are gated on the
`subjcombi.admin` role circle (user tokens only); reads require
authentication only.
"""

import flask

import campus.flask_campus as flask_campus
import campus.yapper
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz
from ..resources import subjcombi as subjcombi_resource

bp = flask.Blueprint('subjcombi', __name__, url_prefix='/subjcombi')

# Lazily initialized yapper - set in init_app() after test fixtures are
# ready. This prevents connection to external services during module
# import in tests.
yapper: campus.yapper.YapperInterface = None  # type: ignore


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise subjcombi routes with the given Flask app/blueprint."""
    global yapper
    yapper = campus.yapper.create()
    app.register_blueprint(bp)


def _actor_id() -> schema.UserID:
    """The authenticated user's id (require_resource_admin has already
    guaranteed a user principal; the explicit check keeps the
    attribution failure loud if the gate is ever reordered).
    """
    user = flask.g.get("current_user")
    if not user or not getattr(user, "id", None):
        raise api_errors.UnauthorizedError(
            "User must be authenticated to change subject-combination "
            "mappings"
        )
    return schema.UserID(user.id)


@bp.put('/<user_id>')
@flask_campus.unpack_request
def set_subjcombi(
        user_id: schema.UserID,
        lessongroup_id: schema.CampusID,
        reason: str | None = None,
        effective_from: str | None = None,
) -> flask_campus.JsonResponse:
    """Set the user's subject-combination mapping.

    Appends an effective-dated record; the previous pending record
    (if any) is superseded. Scheduled records take effect at their
    `effective_from` without any scheduler process.

    Method:
        PUT /subjcombi/{user_id}

    Path Parameters:
        user_id: UserID
            The user whose mapping is set (their campus account email).

    Body Parameters:
        lessongroup_id: CampusID
            The lessongroup to map the user to, by label (the v1
            ttcode, e.g. "2601-H1/P" or a bare class code "2607").
            Stored verbatim; it need not exist in any timetable yet —
            mappings populate ahead of the year's first upload, and
            the version-switch check highlights mappings whose label
            no uploaded timetable carries.
        reason: str | None (optional)
            Free-text change note, preserved on the trail record.
        effective_from: str | None (optional)
            When the mapping takes effect: ISO datetime, or
            `YYYY-MM-DD` for 07:00 school time on that date. Absent =
            immediate.

    Responses:
        201 Created: dict
            The created trail record (includes
            `previous_lessongroup_id` and `actor_id`).

        400 Bad Request: dict
            Empty `lessongroup_id` or malformed `effective_from`.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `subjcombi.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("subjcombi", "set subject-combination mappings")
    actor_id = _actor_id()
    record = subjcombi_resource.set_mapping(
        user_id=user_id,
        lessongroup_id=lessongroup_id,
        actor_id=actor_id,
        effective_from=subjcombi_resource.parse_effective_from(effective_from),
        reason=reason,
    )
    yapper.emit(
        'campus.subjcombi.set',
        {
            "record_id": record[schema.CAMPUS_KEY],
            "user_id": record["user_id"],
            "effective_from": record["effective_from"],
        },
    )
    return subjcombi_resource.to_resource(record), 201


@bp.get('/<user_id>')
@flask_campus.unpack_request
def get_subjcombi(
        user_id: schema.UserID,
        at: str | None = None,
) -> flask_campus.JsonResponse:
    """Get the user's effective subject-combination mapping.

    Resolves through the maintained mapping (its stored label
    translated to a group id through the current timetable), then the
    current timetable's file-derived roster, then unmapped. A mapping
    whose label no current-timetable group carries is an orphan and
    resolves as unmapped.

    Method:
        GET /subjcombi/{user_id}

    Query Parameters:
        at: str | None (optional)
            ISO datetime to resolve the mapping as of (default: now).

    Responses:
        200 OK: dict
            {"user_id": ..., "lessongroup_id": ... | null,
             "source": "mapping" | "roster" | "unmapped"}
    """
    resolved_at = (
        subjcombi_resource.parse_effective_from(at) if at else None
    )
    lessongroup_id, source = subjcombi_resource.resolve(user_id, resolved_at)
    return {
        "user_id": str(user_id),
        "lessongroup_id": lessongroup_id,
        "source": source,
    }, 200


@bp.get('/<user_id>/history')
@flask_campus.unpack_request
def get_subjcombi_history(
        user_id: schema.UserID,
) -> flask_campus.JsonResponse:
    """Get the user's full mapping mutation trail.

    Every record ever appended for the user, newest `effective_from`
    first — including superseded and cancelled records.

    Method:
        GET /subjcombi/{user_id}/history

    Responses:
        200 OK: dict
            {"data": [subjcombi records]}
    """
    records = subjcombi_resource.get_history(user_id)
    return {"data": [subjcombi_resource.to_resource(r) for r in records]}, 200


@bp.get('/')
def list_subjcombi() -> flask_campus.JsonResponse:
    """List every user's current effective mapping, one record per user.

    The bulk read the version-switch check uses to compare stored
    labels against an uploaded timetable's groups. Scheduled (pending)
    switches are not included (GET /pending); mutation trails stay on
    GET /<user_id>/history.

    Method:
        GET /subjcombi/

    Responses:
        200 OK: dict
            {"data": [subjcombi records]}
    """
    records = subjcombi_resource.list_all()
    return {"data": [subjcombi_resource.to_resource(r) for r in records]}, 200


@bp.get('/pending')
@flask_campus.unpack_request
def get_pending() -> flask_campus.JsonResponse:
    """List scheduled mappings not yet effective.

    At most one pending record per user; soonest switch first.

    Method:
        GET /subjcombi/pending

    Responses:
        200 OK: dict
            {"data": [subjcombi records]}
    """
    records = subjcombi_resource.pending()
    return {"data": [subjcombi_resource.to_resource(r) for r in records]}, 200


@bp.delete('/pending/<record_id>')
def cancel_pending(record_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Cancel a pending scheduled mapping.

    The record stays on the trail, tombstoned with `cancelled_at` and
    `cancelled_by`. Already-effective records are immutable history
    and cannot be cancelled (409).

    Method:
        DELETE /subjcombi/pending/{record_id}

    Path Parameters:
        record_id: CampusID
            The subjcombi record to cancel.

    Responses:
        200 OK: dict
            The cancelled record.

        404 Not Found: dict
            Unknown record.

        409 Conflict: dict
            The record is already effective, cancelled, or superseded.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `subjcombi.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("subjcombi", "cancel scheduled mappings")
    actor_id = _actor_id()
    record = subjcombi_resource.cancel(record_id, actor_id)
    yapper.emit(
        'campus.subjcombi.cancel',
        {"record_id": record[schema.CAMPUS_KEY], "user_id": record["user_id"]},
    )
    return subjcombi_resource.to_resource(record), 200
