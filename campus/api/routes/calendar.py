"""campus.api.routes.calendar

API routes for the Calendar resource: the school calendar — one row
per date saying which TT day each cohort runs (or "Free").

Mutations are gated on the `timetable.admin` role circle (user tokens
only): the calendar is a timetable-family resource, edited by the same
committee that owns the timetables — v1's calendar editor lived behind
the committee's Manage Calendar button. Reads require authentication
only (any principal, clients included): timetable grids and the editor
read the calendar server-side.
"""

import flask

import campus.flask_campus as flask_campus
from campus.common.errors import api_errors

from .. import authz
from ..resources import calendar as calendar_resource

bp = flask.Blueprint('calendar', __name__, url_prefix='/calendar')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise calendar routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/')
def get_calendar_range() -> flask_campus.JsonResponse:
    """Get calendar rows in a date range.

    Method:
        GET /calendar/

    Query Parameters:
        from: str | None (optional)
            Range start, inclusive (`YYYY-MM-DD`).
        to: str | None (optional)
            Range end, inclusive (`YYYY-MM-DD`).

    Responses:
        200 OK: dict
            {"days": [CalendarDay, ...]} ordered by date — each row is
            {id, j1_code, j2_code, term_week} with `id` the ISO date.

        400 Bad Request: dict
            A malformed bound.
    """
    days = calendar_resource.get_range(
        flask.request.args.get("from"),
        flask.request.args.get("to"),
    )
    return {"days": days}, 200


@bp.get('/<date>')
def get_calendar_date(date: str) -> flask_campus.JsonResponse:
    """Get one date's calendar row.

    Method:
        GET /calendar/{date}

    Path Parameters:
        date: str
            The calendar date (`YYYY-MM-DD`).

    Responses:
        200 OK: dict
            {id, j1_code, j2_code, term_week}.

        400 Bad Request: dict
            A malformed date.

        404 Not Found: dict
            The date has no calendar row.
    """
    record = calendar_resource.get_date(date)
    if record is None:
        raise api_errors.NotFoundError(
            f"No calendar row for {date}", date=date
        )
    return record, 200


@bp.put('/')
@flask_campus.unpack_request
def upsert_calendar_bulk(days: list[dict]) -> flask_campus.JsonResponse:
    """Upsert many calendar rows at once (the year seed's bulk path).

    Every row is validated before any write, so a bad row anywhere
    leaves the calendar untouched. Rows carrying a date that already
    has a calendar row are updated in place; the rest are created.

    Method:
        PUT /calendar/

    Body Parameters:
        days: list[dict]
            Each row: {date (or id), j1_code?, j2_code?, term_week?} —
            codes from the TT-day vocabulary ("Mon A".."Fri B", "Free")
            or null; `date` is `YYYY-MM-DD`.

    Responses:
        200 OK: dict
            {"upserted": n, "days": [written rows, ordered by date]}.

        400 Bad Request: dict
            A malformed row, an unknown day code, or a duplicate date
            in the payload.
    """
    authz.require_resource_admin("timetable", "edit the school calendar")
    if not isinstance(days, list) or not days:
        raise api_errors.InvalidRequestError(
            "Body must be {\"days\": [{date, j1_code?, j2_code?, "
            "term_week?}, ...]} with at least one row"
        )
    written = calendar_resource.upsert_many(days)
    written.sort(key=lambda record: record["id"])
    return {"upserted": len(written), "days": written}, 200


@bp.put('/<date>')
@flask_campus.unpack_request
def upsert_calendar_date(
        date: str,
        j1_code: str | None = None,
        j2_code: str | None = None,
        term_week: str | None = None,
) -> flask_campus.JsonResponse:
    """Write one date's day-codes, creating the row if absent.

    The day editor's save: both cohorts' codes commit together (v1
    semantics — one press saves both dropdowns). The write is
    idempotent. Changing a day-code changes which TT day runs on that
    date; it does not change which version runs — the timetable
    pointers own that.

    Method:
        PUT /calendar/{date}

    Path Parameters:
        date: str
            The calendar date (`YYYY-MM-DD`).

    Body Parameters:
        j1_code: str | None (optional)
            JC1's TT day code, from the vocabulary ("Mon A".."Fri B",
            "Free"); null leaves the field unset (a day with no
            lessons).
        j2_code: str | None (optional)
            JC2's TT day code, same rules.
        term_week: str | None (optional)
            Term-week label (e.g. "T1 W2"), display data.

    Responses:
        200 OK: dict
            The written row ({id, j1_code, j2_code, term_week}).

        400 Bad Request: dict
            A malformed date or an unknown day code.

        403 Forbidden: dict
            The caller is not a member of the `timetable.admin` circle
            (only user tokens are eligible).
    """
    authz.require_resource_admin("timetable", "edit the school calendar")
    record = calendar_resource.upsert_date(
        date,
        j1_code=j1_code,
        j2_code=j2_code,
        term_week=term_week,
    )
    return record, 200


@bp.delete('/<date>')
def delete_calendar_date(date: str) -> flask_campus.JsonResponse:
    """Remove a date's calendar row (un-seed a date).

    Method:
        DELETE /calendar/{date}

    Path Parameters:
        date: str
            The calendar date (`YYYY-MM-DD`).

    Responses:
        200 OK: dict
            {"deleted": date}.

        400 Bad Request: dict
            A malformed date.

        403 Forbidden: dict
            The caller is not a member of the `timetable.admin` circle
            (only user tokens are eligible).

        404 Not Found: dict
            The date has no calendar row.
    """
    authz.require_resource_admin("timetable", "edit the school calendar")
    calendar_resource.delete_date(date)
    return {"deleted": date}, 200
