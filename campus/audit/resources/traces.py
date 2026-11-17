"""campus.audit.resources.traces

Trace span resource for Campus audit service.

URL path mapping:
    /traces                     → TracesResource (list, search, ingest)
    /traces/{trace_id}          → TraceResource (get_tree)
    /traces/{trace_id}/spans    → TraceSpansResource (list)
    /traces/{trace_id}/spans/{span_id} → SpanResource (get)
"""

__all__ = []

import base64
import json
import typing

import campus.model as model
import campus.storage
from campus.common.errors import api_errors

traces_storage = campus.storage.tables.get_db("spans")

# Page size bounds for trace list/search pagination (issue #698).
# Plain constants for now until a config management strategy is decided;
# requested page sizes are clamped into [1, MAX_PAGE_SIZE].
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 1000

# Traces are grouped from span rows, so the span fetch window gets
# headroom of 10x the requested trace count (approximate heuristic).
_SPAN_FETCH_MULTIPLIER = 10

# Journey membership lives in the free-form tags dict (#803), which the
# storage query language cannot match inside — journey queries post-filter
# spans in Python. This caps how many recent spans such a query scans.
# Fine at the audit UI's scale (~20 viewers); promote journey_id to a
# dedicated column only if this ever becomes slow.
_JOURNEY_SPAN_SCAN_CAP = 20_000


class TraceFilter(typing.NamedTuple):
    """Server-forced trace-read scoping from the caller's API key (#944).

    Opaque match-values bound to the key at mint time and applied to
    every read surface — the caller cannot widen them, only narrow
    them. Each axis, when set, must equal the span's user_id/client_id
    exactly as producers wrote it (plain string equality;
    campus.audit is standalone and never resolves these against
    campus.auth). None on an axis = no bind on that axis;
    (None, None) = unscoped (the operator/admin key class).

    Matching is span-level: a trace is visible iff ANY of its spans
    matches both binds — the same semantics the unscoped search
    endpoint's user_id/client_id filters have always had, so a scoped
    key sees exactly what an unscoped search for its bind would.
    Spans with no identity (null user_id/client_id) match no bind and
    are invisible to scoped keys.

    Every TracesResource read takes a trace_filter as a REQUIRED
    keyword: a read path that forgets to thread it is a TypeError at
    first test run, not a silent unscoped hole.
    """

    user_id: str | None = None
    client_id: str | None = None

    def is_scoped(self) -> bool:
        """True if either axis carries a bind."""
        return self.user_id is not None or self.client_id is not None

    def matches_span(self, span: dict) -> bool:
        """True if the span satisfies both bind axes.

        Args:
            span: Span storage record

        Returns:
            bool: True if every set bind equals the span's attribute.
        """
        return not (
            (self.user_id is not None and span.get("user_id") != self.user_id)
            or (self.client_id is not None and span.get("client_id") != self.client_id)
        )


def _apply_bind(query: dict, trace_filter: TraceFilter) -> bool:
    """Merge the bind axes into a storage query dict.

    The query language is AND-only and keyed by column, so a
    caller-supplied identity filter that disagrees with the bind
    cannot be expressed — that is a guaranteed-empty result, not an
    error: it leaks nothing the endpoint doesn't already reveal, and
    returning the bind's own data for someone else's filter would be
    a correctness bug dressed up as scoping.

    Args:
        query: Query dict to mutate (caller identity filters already
            merged)
        trace_filter: The calling key's forced bind

    Returns:
        bool: False if a caller filter conflicts with the bind on
            some axis (caller should get an empty result).
    """
    if trace_filter.user_id is not None:
        if query.get("user_id") not in (None, trace_filter.user_id):
            return False
        query["user_id"] = trace_filter.user_id
    if trace_filter.client_id is not None:
        if query.get("client_id") not in (None, trace_filter.client_id):
            return False
        query["client_id"] = trace_filter.client_id
    return True


def _span_has_journey(span: dict, journey_id: str) -> bool:
    """Check whether a span record carries the given journey tag (#803)."""
    tags = span.get("tags") or {}
    return tags.get("journey_id") == journey_id


def _span_is_audit_event(span: dict) -> bool:
    """Check whether a span record is an audit event (#941).

    Audit events (audit.apikeys.*, audit.ui.auth.*, audit.traces.*,
    audit.health.check) are ingested as spans in the same table as the
    request traces, one trace per event. The discriminator is the
    event_type tag every event carries; request traces do not.
    """
    tags = span.get("tags") or {}
    return bool(tags.get("event_type"))


def _build_trace_tree(spans: list[dict]) -> model.TraceTree | None:
    """Build a hierarchical tree from flat span list.

    Args:
        spans: Flat list of span records from storage

    Returns:
        TraceTree with root and nested children, or None if no spans
    """
    if not spans:
        return None

    return model.TraceTree.from_spans(spans)


def _build_trace_summaries(spans: list[dict]) -> list[model.TraceSummary]:
    """Build trace summaries from span list.

    Groups spans by trace_id and creates summary records.

    Args:
        spans: Flat list of span records

    Returns:
        List of TraceSummary instances
    """
    # Group spans by trace_id
    traces: dict[str, list[dict]] = {}
    for span in spans:
        trace_id = span["trace_id"]
        if trace_id not in traces:
            traces[trace_id] = []
        traces[trace_id].append(span)

    # Build summaries using TraceSummary.from_spans
    return [
        model.TraceSummary.from_spans(trace_id, trace_spans)
        for trace_id, trace_spans in traces.items()
    ]


class TracePage(typing.NamedTuple):
    """One page of trace summaries plus cursor pagination metadata.

    Attributes:
        summaries: Trace summaries, newest first
        next_cursor: Opaque token for the next page, or None if exhausted
        has_more: True if at least one more trace exists after this page
    """

    summaries: list[model.TraceSummary]
    next_cursor: str | None
    has_more: bool


def _encode_cursor(started_at: str, trace_id: str) -> str:
    """Encode a trace key (started_at, trace_id) as an opaque cursor token."""
    payload = json.dumps({"started_at": started_at, "trace_id": trace_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    """Decode an opaque cursor token into a trace key.

    Args:
        cursor: Cursor token from a previous page response

    Returns:
        (started_at, trace_id) of the last trace on that page

    Raises:
        api_errors.InvalidRequestError: If the token is malformed
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        return payload["started_at"], payload["trace_id"]
    except (ValueError, TypeError, KeyError) as e:
        # binascii.Error and json.JSONDecodeError are both ValueError
        raise api_errors.InvalidRequestError("Invalid cursor token") from e


def _query_trace_page(
        query: dict,
        *,
        limit: int,
        cursor: str | None,
        journey_id: str | None = None,
        include_events: bool = True,
) -> TracePage:
    """Fetch one keyset-paginated page of trace summaries, newest first.

    Traces are grouped from spans and ordered by (started_at, trace_id)
    descending; the cursor encodes the last trace key of the previous
    page. Spans at or before the cursor timestamp are fetched, then
    traces at or after the cursor key are dropped (the query language is
    AND-only, so the tie-break on trace_id happens here).

    Pagination is trace-approximate: the span fetch window is capped at
    limit * _SPAN_FETCH_MULTIPLIER spans, so a trace whose spans straddle
    the window edge may be summarized from partial data.

    When journey_id is given, spans are additionally filtered on the
    tags dict in Python (#803), which makes pages sparser: the fetch
    window holds only ~limit * _SPAN_FETCH_MULTIPLIER recent spans, so
    journey traces further back may be missed. Journey-tagged traces are
    few and recent (login flows), so this is acceptable; the journeys
    view uses journey() with its wider scan cap instead.

    Args:
        query: Storage query dict (filters shared by list and search)
        limit: Page size (clamped by parse_page_size)
        cursor: Opaque token from a previous page, or None for page 1
        journey_id: Optional login-journey tag filter (#803)
        include_events: Whether audit-event traces are included (#941).
            False drops them, so a viewer can show request traces only.

    Returns:
        TracePage with up to limit summaries and next-page metadata
    """
    effective_query = dict(query)
    # (started_at, trace_id) of the last trace on the previous page
    cursor_key = _decode_cursor(cursor) if cursor is not None else None
    if cursor_key is not None:
        effective_query["started_at"] = campus.storage.lte(cursor_key[0])

    try:
        spans = traces_storage.get_matching(
            effective_query,
            order_by="started_at",
            ascending=False,
            limit=limit * _SPAN_FETCH_MULTIPLIER,
        )
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e

    if journey_id is not None:
        spans = [s for s in spans if _span_has_journey(s, journey_id)]
    if not include_events:
        # Audit events are their own traces (one span each), so
        # dropping the span drops the trace with it (#941).
        spans = [s for s in spans if not _span_is_audit_event(s)]

    summaries = _build_trace_summaries(spans)
    summaries.sort(key=lambda s: (s.started_at, s.trace_id), reverse=True)
    if cursor_key is not None:
        # Strictly after the cursor in (started_at, trace_id) walk order
        summaries = [
            s for s in summaries if (s.started_at, s.trace_id) < cursor_key
        ]

    has_more = len(summaries) > limit
    page = summaries[:limit]
    next_cursor = (
        _encode_cursor(page[-1].started_at, page[-1].trace_id)
        if has_more
        else None
    )
    return TracePage(summaries=page, next_cursor=next_cursor, has_more=has_more)


class TracesResource:
    """Represents the traces resource in Campus audit API."""

    @staticmethod
    def parse_page_size(value: str | int | None) -> int:
        """Parse and clamp a page size request parameter.

        Args:
            value: Raw limit value (query params arrive as str)

        Returns:
            Page size clamped into [1, MAX_PAGE_SIZE]; DEFAULT_PAGE_SIZE
            if the value is None or empty

        Raises:
            api_errors.InvalidRequestError: If the value is not an integer
        """
        if value is None or value == "":
            return DEFAULT_PAGE_SIZE
        try:
            limit = int(value)
        except (TypeError, ValueError) as e:
            raise api_errors.InvalidRequestError(
                f"limit must be an integer, got {value!r}"
            ) from e
        return max(1, min(limit, MAX_PAGE_SIZE))

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for trace spans."""
        traces_storage.init_from_model("spans", model.TraceSpan)

    def __getitem__(self, trace_id: str) -> "TraceResource":
        """Get a trace resource by trace ID.

        Maps to URL path: /traces/{trace_id}

        Args:
            trace_id: The 32-char hex trace identifier

        Returns:
            TraceResource instance
        """
        return TraceResource(trace_id)

    def ingest(self, spans: typing.Sequence[model.TraceSpan]) -> dict:
        """Ingest a batch of trace spans.

        Args:
            spans: List of TraceSpan model instances

        Returns:
            Dictionary with created/failed span IDs
        """
        errors = traces_storage.insert_many(
            [span.to_storage() for span in spans]
        )
        if errors:
            # Partial failure - return 207 Multi-Status format
            failed_indices = set(errors.keys())
            return {
                "created": [s.span_id for i, s in enumerate(spans) if i not in failed_indices],
                "failed": [
                    {"span_id": spans[i].span_id, "error": str(errors[i])}
                    for i in failed_indices
                ],
            }
        return {"created": [s.span_id for s in spans]}

    def list(
        self,
        since: str | None = None,
        until: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        *,
        trace_filter: TraceFilter,
    ) -> TracePage:
        """List traces newest first with optional time range filter.

        Args:
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Page size (should be clamped via parse_page_size)
            cursor: Opaque token from a previous page (optional)
            trace_filter: The calling key's forced bind (#944); a
                scoped key sees only traces involving its bind

        Returns:
            TracePage of TraceSummary model instances
        """
        query = {}
        if since and until:
            # Both time bounds provided - use between operator
            query["started_at"] = campus.storage.between(since, until)
        elif since:
            query["started_at"] = campus.storage.gte(since)
        elif until:
            query["started_at"] = campus.storage.lte(until)

        if not _apply_bind(query, trace_filter):
            # Unreachable today (list takes no caller identity
            # filters), kept symmetric with search()
            return TracePage(summaries=[], next_cursor=None, has_more=False)

        return _query_trace_page(query, limit=limit, cursor=cursor)

    def search(
        self,
        path: str | None = None,
        status: int | None = None,
        api_key_id: str | None = None,
        client_id: str | None = None,
        user_id: str | None = None,
        journey_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        include_events: bool = True,
        *,
        trace_filter: TraceFilter,
    ) -> TracePage:
        """Search traces by multiple filter criteria.

        Caller identity filters are intersected with the key's bind
        (#944): a filter that disagrees with the bind on some axis
        yields an empty page (the query language cannot express
        AND-unequal, and it would be a guaranteed-empty match anyway).

        Args:
            path: Filter by endpoint path
            status: Filter by HTTP status code
            api_key_id: Filter by API key
            client_id: Filter by OAuth client
            user_id: Filter by user
            journey_id: Filter by login-journey tag (#803); matched
                against spans.tags in Python
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Page size (should be clamped via parse_page_size)
            cursor: Opaque token from a previous page (optional)
            include_events: Whether audit-event traces are included
                (#941). The versioned API keeps them — the trail is
                queryable by design; a viewer can ask for request
                traces only.
            trace_filter: The calling key's forced bind (#944)

        Returns:
            TracePage of TraceSummary model instances
        """
        query = {}
        if path:
            query["path"] = path
        if status is not None:
            query["status_code"] = status
        if api_key_id:
            query["api_key_id"] = api_key_id
        if client_id:
            query["client_id"] = client_id
        if user_id:
            query["user_id"] = user_id
        if since and until:
            # Both time bounds provided - use between operator
            query["started_at"] = campus.storage.between(since, until)
        elif since:
            query["started_at"] = campus.storage.gte(since)
        elif until:
            query["started_at"] = campus.storage.lte(until)

        if not _apply_bind(query, trace_filter):
            # Caller named an identity that disagrees with the bind:
            # guaranteed no matches, so skip the query entirely.
            return TracePage(summaries=[], next_cursor=None, has_more=False)

        return _query_trace_page(
            query,
            limit=limit,
            cursor=cursor,
            journey_id=journey_id,
            include_events=include_events,
        )

    def journey(
            self,
            journey_id: str,
            *,
            trace_filter: TraceFilter,
    ) -> "list[model.TraceSummary]":
        """List every trace in one login journey, oldest first (#803).

        A journey is the set of traces whose spans carry
        tags.journey_id == journey_id — the browser hops of one login
        flow plus its server-to-server /token exchange. Membership is
        matched in Python from the tags dict (zero migrations); the scan
        covers the most recent _JOURNEY_SPAN_SCAN_CAP spans, which is
        the whole table at this service's scale.

        The key's bind (#944) is applied to the member spans BEFORE
        summaries and counts are built, so a scoped key's trace_count
        never leaks how many of another user's traces sit in the
        journey.

        Args:
            journey_id: The campus_journey cookie value to group by
            trace_filter: The calling key's forced bind (#944)

        Returns:
            TraceSummary instances in (started_at, trace_id) order
        """
        try:
            spans = traces_storage.get_matching(
                {},
                order_by="started_at",
                ascending=False,
                limit=_JOURNEY_SPAN_SCAN_CAP,
            )
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        member_spans = [
            s for s in spans if _span_has_journey(s, journey_id)
        ]
        if trace_filter.is_scoped():
            member_spans = [
                s for s in member_spans if trace_filter.matches_span(s)
            ]
        summaries = _build_trace_summaries(member_spans)
        summaries.sort(key=lambda s: (s.started_at, s.trace_id))
        return summaries


class TraceResource:
    """Represents a single trace in Campus audit API.

    Maps to URL path: /traces/{trace_id}/
    """

    def __init__(self, trace_id: str):
        self.trace_id = trace_id

    def __getitem__(self, key: str) -> "TraceSpansResource":
        """Get the spans resource for this trace.

        Maps to URL path: /traces/{trace_id}/spans

        Args:
            key: Must be "spans"

        Returns:
            TraceSpansResource instance
        """
        if key != "spans":
            raise api_errors.NotFoundError(
                f"Unknown resource '{key}' for trace {self.trace_id}"
            )
        return TraceSpansResource(self)

    def get_tree(self, *, trace_filter: TraceFilter) -> model.TraceTree | None:
        """Get full trace tree with nested children.

        A scoped key (#944) that matches no span of the trace gets
        None — indistinguishable from a missing trace, so existence
        never leaks.

        Args:
            trace_filter: The calling key's forced bind (#944)

        Returns:
            TraceTree with root and nested children, or None if not
            found (or invisible to this key)
        """
        try:
            spans = traces_storage.get_matching({"trace_id": self.trace_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        if trace_filter.is_scoped() and not any(
                trace_filter.matches_span(s) for s in spans
        ):
            return None

        return _build_trace_tree(spans)

    def get(self, *, trace_filter: TraceFilter) -> model.TraceTree | None:
        """Get trace summary (alias for get_tree).

        Args:
            trace_filter: The calling key's forced bind (#944)

        Returns:
            TraceTree or None
        """
        return self.get_tree(trace_filter=trace_filter)


class TraceSpansResource:
    """Represents the spans within a trace.

    Maps to URL path: /traces/{trace_id}/spans
    """

    def __init__(self, parent: TraceResource):
        self._parent = parent

    def __getitem__(self, span_id: str) -> "SpanResource":
        """Get a single span by span_id.

        Maps to URL path: /traces/{trace_id}/spans/{span_id}/

        Args:
            span_id: The 16-char hex span identifier

        Returns:
            SpanResource instance
        """
        return SpanResource(self, span_id)

    def list(self, *, trace_filter: TraceFilter) -> list[model.TraceSpan]:
        """List all spans in the trace (flat list).

        Visibility is trace-level (#944): if any span of the trace
        matches the bind, the whole trace's spans are returned (the
        same view an unscoped search for the bind renders); if none
        match, the trace is invisible and this raises NotFoundError —
        indistinguishable from a missing trace, so existence never
        leaks.

        Args:
            trace_filter: The calling key's forced bind (#944)

        Returns:
            List of TraceSpan model instances

        Raises:
            api_errors.NotFoundError: If the trace does not exist or
                is invisible to this key.
        """
        try:
            records = traces_storage.get_matching({"trace_id": self._parent.trace_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        if trace_filter.is_scoped() and not any(
                trace_filter.matches_span(s) for s in records
        ):
            raise api_errors.NotFoundError(
                f"Trace {self._parent.trace_id} not found"
            )

        return [model.TraceSpan.from_storage(record) for record in records]


class SpanResource:
    """Represents a single span within a trace.

    Maps to URL path: /traces/{trace_id}/spans/{span_id}
    """

    def __init__(self, parent: TraceSpansResource, span_id: str):
        self._parent = parent
        self.span_id = span_id

    def get(self, *, trace_filter: TraceFilter) -> model.TraceSpan | None:
        """Get the span details.

        Visibility is trace-level (#944): the span is returned only if
        some span of its trace matches the bind — None otherwise, so
        existence never leaks.

        Args:
            trace_filter: The calling key's forced bind (#944)

        Returns:
            TraceSpan model instance or None if not found (or
            invisible to this key)
        """
        try:
            # Get by id (storage PK, which is aliased to span_id)
            record = traces_storage.get_by_id(self.span_id)
        except campus.storage.errors.NotFoundError:
            return None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        # Verify it belongs to this trace
        if record.get("trace_id") != self._parent._parent.trace_id:
            return None

        if trace_filter.is_scoped():
            try:
                siblings = traces_storage.get_matching(
                    {"trace_id": record["trace_id"]}
                )
            except campus.storage.errors.StorageError as e:
                raise api_errors.InternalError.from_exception(e) from e
            if not any(trace_filter.matches_span(s) for s in siblings):
                return None

        return model.TraceSpan.from_storage(record)
