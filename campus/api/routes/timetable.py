"""campus.api.routes.timetable

API routes for the Timetable resource.
"""

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz
from ..resources import timetable as timetable_resource
from ..resources.timetable import parse_effective_from

bp = flask.Blueprint('timetable', __name__, url_prefix='/timetable')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise timetable routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/')
def get_pointers() -> flask_campus.JsonResponse:
    """Get the active-timetable pointer state.

    The deployment's current timetable and the pending switch, if any.
    Pointers are an effective-dated trail: a scheduled switch flips as
    a read-time fact at its effective_from.

    Method:
        GET /timetable/

    Responses:
        200 OK: dict
            {"current": timetable_id | null, "next": timetable_id |
            null, "effective_from": datetime | null}
    """
    return timetable_resource.pointers_state(), 200


@bp.patch('/')
def patch_pointers() -> flask_campus.JsonResponse:
    """Patch one timetable pointer: flip current or schedule next.

    Exactly one pointer key per call. `{current}` flips immediately
    (trail row effective now). `{next, effective_from?}` schedules or
    reschedules the pending switch — date-only values apply at 07:00
    school time; an absent effective_from stages an undated switch
    that flips only when pointed at manually. `{next: null}` cancels
    the pending switch.

    Method:
        PATCH /timetable/

    Body Parameters:
        current: CampusID (alternative)
            The timetable ID to make current, effective now.
        next: CampusID | null (alternative)
            The timetable ID to schedule as the pending switch, or
            null to cancel the pending switch.
        effective_from: str | None (optional, with `next` only)
            When the pending switch applies.

    Responses:
        200 OK: dict
            The resulting pointer state (same shape as GET /timetable/).

        400 Bad Request: dict
            Both keys, unknown fields, `effective_from` without a
            `next` id, or a malformed `effective_from`.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("timetable", "change the active timetable")
    actor_id = _require_user_id()
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        raise api_errors.InvalidRequestError(
            "Patch body required: send {\"current\": id} or "
            "{\"next\": id, \"effective_from\"?} (or {\"next\": null} "
            "to cancel the pending switch)"
        )
    unknown = set(payload) - {"current", "next", "effective_from"}
    if unknown:
        raise api_errors.InvalidRequestError(
            f"Unknown fields: {sorted(unknown)}"
        )
    if "current" in payload and "next" in payload:
        raise api_errors.InvalidRequestError(
            "Patch exactly one pointer: 'current' or 'next', not both"
        )
    if "current" in payload:
        value = payload["current"]
        if not value:
            raise api_errors.InvalidRequestError(
                "'current' cannot be unset; point it at a timetable id"
            )
        timetable_resource.flip_current(value, actor_id=actor_id)
    elif "next" in payload:
        value = payload["next"]
        if value is None:
            if payload.get("effective_from") is not None:
                raise api_errors.InvalidRequestError(
                    "'effective_from' only applies with a 'next' "
                    "timetable id"
                )
            timetable_resource.cancel_next(actor_id=actor_id)
        else:
            raw = payload.get("effective_from")
            timetable_resource.schedule_next(
                value,
                effective_from=parse_effective_from(raw) if raw else None,
                actor_id=actor_id,
            )
    else:
        raise api_errors.InvalidRequestError(
            "Patch body required: send 'current' or 'next'"
        )
    return timetable_resource.pointers_state(), 200


@bp.get('/metadata/')
def list_timetable_metadata() -> flask_campus.JsonResponse:
    """List all timetable metadata records.

    Method:
        GET /timetable/metadata/

    Responses:
        200 OK: dict
            {"data": [timetable metadata resources]}
    """
    result = timetable_resource.list()
    return {"data": [timetable.to_resource() for timetable in result]}, 200


@bp.get('/current')
@flask_campus.unpack_request
def get_current() -> flask_campus.JsonResponse:
    """Get the currently active timetable ID.

    Method:
        GET /timetable/current

    Query Parameters:
        None

    Responses:
        200 OK: dict
            {"value": timetable_id}
    """
    timetable_id = timetable_resource.get_current()
    return {'value': timetable_id}, 200


@bp.get('/next')
def get_next() -> flask_campus.JsonResponse:
    """Get the next scheduled timetable and its effective date.

    Method:
        GET /timetable/next

    Responses:
        200 OK: dict
            {"value": timetable_id | null, "effective_from": datetime |
            null}
    """
    nxt = timetable_resource.get_next()
    if nxt is None:
        return {'value': None, 'effective_from': None}, 200
    return {
        'value': nxt["timetable_id"],
        'effective_from': nxt["effective_from"],
    }, 200


def _require_user_id() -> schema.UserID:
    """The authenticated user's id (require_resource_admin has already
    guaranteed a user principal; the explicit check keeps the
    attribution failure loud if the gate is ever reordered).
    """
    user = flask.g.get("current_user")
    if not user or not getattr(user, "id", None):
        raise api_errors.UnauthorizedError(
            "User must be authenticated to change the active timetable"
        )
    return schema.UserID(user.id)

@bp.post('/')
@flask_campus.unpack_request
def new(
    metadata: dict,
    data: dict
) -> flask_campus.JsonResponse:
    """Create a new timetable.

    Method:
        POST /timetable/

    Body Parameters:
        metadata: dict
            Metadata for the timetable, e.g. start and end date.

        data: dict
            The actual timetable data, e.g. lesson groups and entries.

    Responses:
        200 OK: dict
           {"data": timetable resource with labeled entries}

        400 Bad Request: dict
            {"error": error message}

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("timetable", "create timetables")
    if "lessongroups" not in data:
        details = {}
        if "lesson_groups" in data:
            details["suggestion"] = (
                "Hint: 'lesson_groups' should be renamed to "
                "'lessongroups'"
            )
        raise api_errors.InvalidRequestError(
            "'data' object requires 'lessongroups' property",
            **details
        )
    timetable = timetable_resource.new(
        metadata=metadata,
        lessongroups=data["lessongroups"]
    )
    return {"data": timetable.to_resource()}, 200

@bp.get('/<timetable_id>/')
@flask_campus.unpack_request
def get_timetable(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Returns timetable metadata and labeled entries in a single JSON object.

    Method:
        GET /timetable/<timetable_id>/
    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable to retrieve.
    Responses:
        200 OK: dict
            {"timetable": timetable resource}
    """
    timetable = timetable_resource[timetable_id].get()
    return {"timetable": timetable.to_resource()}, 200
    

@bp.get('/<timetable_id>/entries')
@flask_campus.unpack_request
def get_timetable_entries(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """List all timetable entries for a specific timetable and user.

    Method:
        GET /timetable/<timetable_id>/entries

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable to retrieve.

    Responses:
        200 OK: dict
            {"entries": [timetable entry resources with labels]}
    """
    result = timetable_resource[timetable_id].entries.list()
    return {'entries': [entry.to_resource() for entry in result]}, 200
    

@bp.get('/<timetable_id>/metadata')
@flask_campus.unpack_request
def get_timetable_metadata(timetable_id: schema.CampusID):
    """Get metadata for a specific timetable.

    Method:
        GET /timetable/<timetable_id>/metadata

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Responses:
        200 OK: dict
            timetable metadata resource
    """
    timetable = timetable_resource[timetable_id].metadata.get()
    return timetable.to_resource(), 200

@bp.patch('/<timetable_id>/metadata')
@flask_campus.unpack_request
def set_metadata(
        timetable_id: schema.CampusID,
        start_date: schema.DateTime,
        end_date: schema.DateTime,
) -> flask_campus.JsonResponse:
    """Update metadata for a specific timetable.

    Method:
        PATCH /timetable/<timetable_id>/metadata

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Body Parameters:
        start_date: DateTime
            The new start date of the timetable.
        end_date: DateTime
            The new end date of the timetable.

    Responses:
        200 OK: dict
            {}

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("timetable", "edit timetable metadata")
    timetable_resource[timetable_id].metadata.update(
        start_date=start_date,
        end_date=end_date
    )
    return {}, 200
