"""campus.api.routes.timetable

API routes for the Timetable resource.
"""

import datetime
import io

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import utc_time

from .. import authz
from ..resources import subjcombi as subjcombi_resource
from ..resources import timetable as timetable_resource
from ..resources.files import FileResource
from ..resources.timetable import parse_effective_from

bp = flask.Blueprint('timetable', __name__, url_prefix='/timetable')

# Attachment content responses cache briefly, mirroring the files
# routes' budget: attachment slugs are immutable per upload (removal is
# explicit), so replacements never invalidate a cached copy mid-budget.
ATTACHMENT_CONTENT_CACHE_MAX_AGE = 60


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


@bp.get('/me')
@flask_campus.unpack_request
def get_my_timetable(at: str | None = None) -> flask_campus.JsonResponse:
    """Resolve the signed-in user's effective timetable view (#592).

    The subject is the bearer token's user — no user_id parameter.
    The current leg resolves the active timetable version and the
    user's effective subject combination (maintained mapping, else the
    version's file-derived roster) at `at` (default now). The next leg
    shows the state at the earliest pending change — a scheduled
    version switch or the user's scheduled subjcombi record, whichever
    comes first — with `change_type` telling the two planning cases
    apart (whole-school vs affected-students-only). Entries are fetched
    separately via /timetable/{id}/entries and filtered by
    lessongroup_id.

    Method:
        GET /timetable/me

    Query Parameters:
        at: str | None (optional)
            ISO datetime to resolve the view as of (default now).

    Responses:
        200 OK: dict
            {"current": {timetable_id, lessongroup_id, source},
             "next": null | {timetable_id, lessongroup_id, source,
             effective_from, change_type: "timetable" | "subjcombi" |
             "both"}}

        401 Unauthorized: None
            No authenticated user.
    """
    user = flask.g.get("current_user")
    if not user or not getattr(user, "id", None):
        raise api_errors.UnauthorizedError(
            "Sign in to resolve your timetable"
        )
    user_id = schema.UserID(user.id)
    now_dt = parse_effective_from(at) if at else utc_time.now()

    def _leg(at_dt: datetime.datetime) -> dict:
        timetable_id = timetable_resource.get_current(at_dt)
        lessongroup_id, source = subjcombi_resource.resolve(user_id, at_dt)
        return {
            "timetable_id": timetable_id,
            "lessongroup_id": lessongroup_id,
            "source": source,
        }

    current_leg = _leg(now_dt)

    # Earliest pending change after now: a dated version switch or the
    # user's earliest scheduled subjcombi record. An undated staged
    # switch has no known flip time and is not renderable as "next".
    switch_candidates: list[datetime.datetime] = []
    pending_pointer = timetable_resource.get_next()
    if pending_pointer and pending_pointer["effective_from"]:
        switch_candidates.append(
            utc_time.from_rfc3339(pending_pointer["effective_from"])
        )
    pending_records = subjcombi_resource.pending(user_id)
    if pending_records:
        switch_candidates.append(
            utc_time.from_rfc3339(pending_records[0]["effective_from"])
        )
    if not switch_candidates:
        return {"current": current_leg, "next": None}, 200

    switch_dt = min(switch_candidates)
    next_leg = _leg(switch_dt)
    version_changed = (
        next_leg["timetable_id"] != current_leg["timetable_id"]
    )
    group_changed = (
        next_leg["lessongroup_id"] != current_leg["lessongroup_id"]
    )
    if version_changed and group_changed:
        change_type = "both"
    elif version_changed:
        change_type = "timetable"
    else:
        change_type = "subjcombi"
    next_leg.update({
        "effective_from": utc_time.to_rfc3339(switch_dt),
        "change_type": change_type,
    })
    return {"current": current_leg, "next": next_leg}, 200


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

    Lessongroup ids are reused by label across allocations (#592):
    a label that already has a group row — from any earlier allocation
    — keeps its id, and the row moves to the new allocation, so
    subjcombi mappings keyed by lessongroup_id survive version
    switches. The payload shape is unchanged (label/members/entries).

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
            {"error": error message} — missing 'lessongroups',
            missing group keys, or a label repeated within the
            payload (one label anchors one group).

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).

        409 Conflict: dict
            A payload label is already claimed by two or more group
            rows — historical drift; clean up the duplicate-label
            rows and retry.
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


@bp.delete('/<timetable_id>/')
def delete_timetable(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a timetable version and all of its rows (#1088).

    Cascades the version's entries, group members and lessongroup rows,
    then the version itself. This is the cleanup surface for the
    label-drift create 409: stale duplicate-label rows are owned by the
    superseded versions that minted them, so deleting those versions
    clears the drift. A group row that a later create reused is owned
    by that later version and survives.

    Refuses to delete the version the current or next pointer names —
    move/cancel the pointer first. This action is destructive and
    cannot be undone.

    Method:
        DELETE /timetable/<timetable_id>/

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable version to delete.

    Responses:
        200 OK: dict
            Empty JSON object indicating successful deletion.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).

        404 Not Found: dict
            {"error": error message} — unknown timetable_id.

        409 Conflict: dict
            {"error": error message} — the version is the current or
            next pointer target.
    """
    authz.require_resource_admin("timetable", "delete timetables")
    timetable_resource.delete(timetable_id)
    return {}, 200


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
def set_metadata(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Update metadata fields for a specific timetable.

    A subset update: send any of `label`, `start_date`, `end_date` —
    only the fields present in the body change. The label is the
    committee's user-given display name (timetable-v2 Manage
    Timetables); `null` clears it back to unnamed. `filename` is the
    allocation's identity and is not updatable.

    Method:
        PATCH /timetable/<timetable_id>/metadata

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Body Parameters:
        label: str | None (optional)
            The new display name, or null to clear it. An empty
            string is rejected — clear with null instead.
        start_date: DateTime (optional)
            The new start date of the timetable.
        end_date: DateTime (optional)
            The new end date of the timetable.

    Responses:
        200 OK: dict
            The updated metadata resource.

        400 Bad Request: dict
            {"error": error message} — empty body, unknown fields, a
            `filename` patch attempt, or an empty `label` string.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("timetable", "edit timetable metadata")
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        raise api_errors.InvalidRequestError(
            "Patch body required: send any of 'label', 'start_date', "
            "'end_date' (only the fields present change)"
        )
    if "filename" in payload:
        raise api_errors.InvalidRequestError(
            "'filename' is the allocation's identity and cannot be "
            "changed; import a new timetable version instead"
        )
    unknown = set(payload) - {"label", "start_date", "end_date"}
    if unknown:
        raise api_errors.InvalidRequestError(
            f"Unknown fields: {sorted(unknown)}"
        )
    if "label" in payload:
        label = payload["label"]
        if label is not None and not str(label).strip():
            raise api_errors.InvalidRequestError(
                "'label' must be a non-empty string or null (clear it "
                "with null, not an empty string)"
            )
    timetable_resource[timetable_id].metadata.update(**payload)
    return timetable_resource[timetable_id].metadata.get().to_resource(), 200


def _upload_content_type() -> str:
    """The request's Content-Type header, defaulting to octet-stream."""
    content_type = flask.request.content_type
    if not content_type:
        return "application/octet-stream"
    # Strip parameters (e.g. "; charset=...") for storage; the MIME
    # type is what gets served back.
    return content_type.split(";", 1)[0].strip() or "application/octet-stream"


def _upload_principals() -> tuple[str, str | None]:
    """The authenticated (client, user) pair for attachment uploads.

    The timetable blueprint sits behind the api authenticator, so a
    client is always present; the user is None for client-credential
    calls. Admin-gated routes have already established a user.
    """
    client = flask.g.get("current_client")
    client_id = str(getattr(client, "id", "") or "")
    if not client_id:
        raise api_errors.UnauthorizedError(
            "Attachment uploads require an authenticated client"
        )
    user = flask.g.get("current_user")
    user_id = getattr(user, "id", None)
    return client_id, str(user_id) if user_id else None


@bp.post('/<timetable_id>/attachments/')
def add_timetable_attachment(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Attach a file (PDF, image, …) to a timetable version.

    The body is the raw file content; the `filename` query parameter
    carries the committee's original filename (what the card shows)
    and the Content-Type header is stored and served back. Each upload
    mints a new attachment — re-uploading the same filename adds a
    second copy rather than replacing one (removal is explicit).

    Method:
        POST /timetable/<timetable_id>/attachments/

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Query Parameters:
        filename: str (required)
            The attachment's display filename.

    Body:
        Raw bytes (any Content-Type; defaults to application/octet-stream).

    Responses:
        201 Created: dict
            The attachment record (a files-backend record; the
            attachment id is the record's `id`).

        400 Bad Request: dict
            {"error": error message} — missing filename or empty body.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).

        404 Not Found: dict
            {"error": error message} — unknown timetable_id.
    """
    authz.require_resource_admin("timetable", "add timetable attachments")
    client_id, user_id = _upload_principals()
    filename = (flask.request.args.get("filename") or "").strip()
    if not filename:
        raise api_errors.InvalidRequestError(
            "Attachment filename required: pass it as the ?filename= "
            "query parameter"
        )
    record = timetable_resource[timetable_id].attachments.add(
        data=flask.request.get_data(cache=False),
        filename=filename,
        content_type=_upload_content_type(),
        client_id=client_id,
        user_id=user_id,
    )
    return FileResource.to_resource(record), 201


@bp.get('/<timetable_id>/attachments/')
def list_timetable_attachments(timetable_id: schema.CampusID) -> flask_campus.JsonResponse:
    """List a timetable version's attachments, newest first.

    Method:
        GET /timetable/<timetable_id>/attachments/

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.

    Responses:
        200 OK: dict
            {"data": [attachment records]} — files-backend records
            under the version's attachments namespace.

        404 Not Found: dict
            {"error": error message} — unknown timetable_id.
    """
    result = timetable_resource[timetable_id].attachments.list()
    return {"data": [FileResource.to_resource(record) for record in result]}, 200


@bp.get('/<timetable_id>/attachments/<attachment_id>/content/')
def get_timetable_attachment_content(
        timetable_id: schema.CampusID,
        attachment_id: schema.CampusID,
) -> flask.Response:
    """Serve an attachment's bytes.

    The response carries the stored Content-Type, an ETag and the same
    brief cache budget as the files routes (attachment slugs are
    immutable per upload).

    Method:
        GET /timetable/<timetable_id>/attachments/<attachment_id>/content/

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.
        attachment_id: CampusID
            The attachment id (the underlying file record's id).

    Responses:
        200 OK: bytes
            The attachment content with its stored Content-Type.

        404 Not Found: dict
            {"error": error message} — unknown id, or the attachment
            belongs to a different timetable.
    """
    data, record = timetable_resource[timetable_id].attachments.get_content(
        attachment_id
    )
    etag = f'{record["size"]}-{record["updated_at"]}'
    return flask.send_file(
        io.BytesIO(data),
        mimetype=record["content_type"],
        conditional=True,
        max_age=ATTACHMENT_CONTENT_CACHE_MAX_AGE,
        etag=etag,
    )


@bp.delete('/<timetable_id>/attachments/<attachment_id>/')
def delete_timetable_attachment(
        timetable_id: schema.CampusID,
        attachment_id: schema.CampusID,
) -> flask_campus.JsonResponse:
    """Remove an attachment from a timetable version.

    Deletes the underlying file record and its content. Removing an
    attachment never touches the timetable itself.

    Method:
        DELETE /timetable/<timetable_id>/attachments/<attachment_id>/

    Path Parameters:
        timetable_id: CampusID
            The ID of the timetable.
        attachment_id: CampusID
            The attachment id to remove.

    Responses:
        200 OK: dict
            Empty JSON object indicating successful removal.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `timetable.admin` circle (only user tokens are eligible).

        404 Not Found: dict
            {"error": error message} — unknown id, or the attachment
            belongs to a different timetable.
    """
    authz.require_resource_admin("timetable", "remove timetable attachments")
    timetable_resource[timetable_id].attachments.delete(attachment_id)
    return {}, 200
