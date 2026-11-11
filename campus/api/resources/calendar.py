"""campus.api.resources.calendar

School-calendar resource for Campus API.

One row per calendar date (campus.model.CalendarDay, keyed by the ISO
date itself): which TT day each cohort runs, or "Free" (the NSD).
Consumers read the calendar to resolve a date's effective TT day —
the Manage Calendar editor reads and writes one date at a time, and a
year seed writes whole terms ahead of the school year via the bulk
upsert. Which VERSION a date runs is not calendar data: the timetable
pointer trail owns that, exactly as v1's calendar-editor docs note
("changing a day-code does not change the version").

Writes validate the date format and the day-code vocabulary
(DAY_CODE_VOCABULARY); a write to a well-formed date creates the row.
v1's editor could not create rows — the API can, which is what makes
seeding a school year possible at all (the v1 docs' open question:
"how a new year's calendar rows come to exist at all" — the seed).
"""

import datetime
import re
import typing

import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.model.calendar import DAY_CODE_VOCABULARY
from campus.storage.documents.interface import PK

calendar_table = campus.storage.get_table("calendar")

_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _validated_date(raw: str) -> str:
    """Validate + normalise an ISO calendar date (`YYYY-MM-DD`).

    Strictly hyphenated: `date.fromisoformat` alone would also accept
    the basic format (`20270111`), and the date string is the row's
    primary key — one spelling per date, or range filters and the
    month grid disagree.
    """
    text = (raw or "").strip()
    if not _ISO_DATE_RE.fullmatch(text):
        raise api_errors.InvalidRequestError(
            f"Invalid calendar date {raw!r}: use YYYY-MM-DD"
        )
    try:
        datetime.date.fromisoformat(text)
    except ValueError as e:
        raise api_errors.InvalidRequestError(
            f"{text} is not a real calendar date"
        ) from e
    return text


def _validated_code(value: str | None, cohort: str) -> str | None:
    """Validate one cohort's day code against the vocabulary."""
    if value is None:
        return None
    if value not in DAY_CODE_VOCABULARY:
        raise api_errors.InvalidRequestError(
            f"Invalid {cohort} code {value!r}: use one of "
            f"{', '.join(DAY_CODE_VOCABULARY)}, or null to leave the "
            "field unset"
        )
    return str(value)


class CalendarResource:
    """The school calendar: date-keyed TT day-code rows."""

    @classmethod
    def init_storage(cls) -> None:
        """Create the calendar table if absent (self-heal startup)."""
        calendar_table.init_from_model("calendar", model.CalendarDay)

    @staticmethod
    def _validated_row(day: dict) -> str:
        """Validate one seed row; return its normalised date key."""
        if not isinstance(day, dict):
            raise api_errors.InvalidRequestError(
                "Each calendar day must be an object with a `date` "
                "(or `id`) and optional j1_code/j2_code/term_week"
            )
        raw_date = day.get("date") or day.get("id")
        if not raw_date:
            raise api_errors.InvalidRequestError(
                "Each calendar day needs a `date` (YYYY-MM-DD)"
            )
        date_key = _validated_date(str(raw_date))
        _validated_code(day.get("j1_code"), "j1_code")
        _validated_code(day.get("j2_code"), "j2_code")
        term_week = day.get("term_week")
        if term_week is not None and not str(term_week).strip():
            raise api_errors.InvalidRequestError(
                "term_week must be a non-empty label or null"
            )
        return date_key

    def get_date(self, date_raw: str) -> dict | None:
        """The calendar row for one date, or None if the date has none."""
        try:
            return calendar_table.get_by_id(_validated_date(date_raw))
        except campus.storage.errors.NotFoundError:
            return None

    def get_range(
        self,
        from_raw: str | None,
        to_raw: str | None,
    ) -> list[dict]:
        """The rows whose dates fall in [from, to], inclusive, ordered.

        Both bounds optional; absent bounds are open. The calendar is
        small (a school year is ~200 rows), so filtering in Python over
        the whole table is fine and keeps the storage contract to
        equality queries.
        """
        date_from = _validated_date(from_raw) if from_raw else None
        date_to = _validated_date(to_raw) if to_raw else None
        rows = [
            record
            for record in calendar_table.get_matching({})
            if (date_from is None or record["id"] >= date_from)
            and (date_to is None or record["id"] <= date_to)
        ]
        rows.sort(key=lambda record: record["id"])
        return rows

    def _write_row(self, date_key: str, fields: dict) -> dict:
        """Insert or update one row; returns the row as stored.

        `created_at` is stamped on insert and never overwritten by an
        update (the storage contract: every row carries one; the
        table interface assumes it, and init_from_model emits it NOT
        NULL). Updates write only the calendar fields, preserving the
        original timestamp.
        """
        try:
            calendar_table.get_by_id(date_key)
        except campus.storage.errors.NotFoundError:
            record = {
                PK: date_key,
                "created_at": schema.DateTime.utcnow(),
                **fields,
            }
            calendar_table.insert_one(record)
        else:
            calendar_table.update_by_id(date_key, fields)
        return calendar_table.get_by_id(date_key)

    def upsert_date(
        self,
        date_raw: str,
        *,
        j1_code: str | None = None,
        j2_code: str | None = None,
        term_week: str | None = None,
    ) -> dict:
        """Write one date's day-codes, creating the row if absent.

        Codes must be in DAY_CODE_VOCABULARY (or None to leave the
        field unset — the day editor's "select schedule", which behaves
        as a day with no lessons). The write is idempotent: the same
        codes twice leave the same row.
        """
        date_key = _validated_date(date_raw)
        return self._write_row(
            date_key,
            {
                "j1_code": _validated_code(j1_code, "j1_code"),
                "j2_code": _validated_code(j2_code, "j2_code"),
                "term_week": str(term_week).strip() if term_week else None,
            },
        )

    def upsert_many(self, days: typing.Iterable[dict]) -> list[dict]:
        """Validate and upsert many rows (the year seed's bulk path).

        Validation happens for every row BEFORE any write, so a bad row
        anywhere leaves the calendar untouched.
        """
        validated: list[dict] = []
        seen: set[str] = set()
        for day in days:
            date_key = self._validated_row(day)
            if date_key in seen:
                raise api_errors.InvalidRequestError(
                    f"Duplicate calendar date in payload: {date_key}"
                )
            seen.add(date_key)
            validated.append(
                {
                    "id": date_key,
                    "j1_code": _validated_code(day.get("j1_code"), "j1_code"),
                    "j2_code": _validated_code(day.get("j2_code"), "j2_code"),
                    "term_week": (
                        str(day["term_week"]).strip() if day.get("term_week") else None
                    ),
                }
            )
        written: list[dict] = []
        for record in validated:
            fields = {
                "j1_code": record["j1_code"],
                "j2_code": record["j2_code"],
                "term_week": record["term_week"],
            }
            written.append(self._write_row(record["id"], fields))
        return written

    def delete_date(self, date_raw: str) -> None:
        """Remove a date's row (the committee un-seeding a date)."""
        date_key = _validated_date(date_raw)
        try:
            calendar_table.get_by_id(date_key)
        except campus.storage.errors.NotFoundError as e:
            raise api_errors.NotFoundError(
                f"No calendar row for {date_key}",
                date=date_key,
            ) from e
        calendar_table.delete_by_id(date_key)
