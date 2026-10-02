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

    Args:
        query: Storage query dict (filters shared by list and search)
        limit: Page size (clamped by parse_page_size)
        cursor: Opaque token from a previous page, or None for page 1

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
    ) -> TracePage:
        """List traces newest first with optional time range filter.

        Args:
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Page size (should be clamped via parse_page_size)
            cursor: Opaque token from a previous page (optional)

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

        return _query_trace_page(query, limit=limit, cursor=cursor)

    def search(
        self,
        path: str | None = None,
        status: int | None = None,
        api_key_id: str | None = None,
        client_id: str | None = None,
        user_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> TracePage:
        """Search traces by multiple filter criteria.

        Args:
            path: Filter by endpoint path
            status: Filter by HTTP status code
            api_key_id: Filter by API key
            client_id: Filter by OAuth client
            user_id: Filter by user
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Page size (should be clamped via parse_page_size)
            cursor: Opaque token from a previous page (optional)

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

        return _query_trace_page(query, limit=limit, cursor=cursor)


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

    def get_tree(self) -> model.TraceTree | None:
        """Get full trace tree with nested children.

        Returns:
            TraceTree with root and nested children, or None if not found
        """
        try:
            spans = traces_storage.get_matching({"trace_id": self.trace_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return _build_trace_tree(spans)

    def get(self) -> model.TraceTree | None:
        """Get trace summary (alias for get_tree).

        Returns:
            TraceTree or None
        """
        return self.get_tree()


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

    def list(self) -> list[model.TraceSpan]:
        """List all spans in the trace (flat list).

        Returns:
            List of TraceSpan model instances
        """
        try:
            records = traces_storage.get_matching({"trace_id": self._parent.trace_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return [model.TraceSpan.from_storage(record) for record in records]


class SpanResource:
    """Represents a single span within a trace.

    Maps to URL path: /traces/{trace_id}/spans/{span_id}
    """

    def __init__(self, parent: TraceSpansResource, span_id: str):
        self._parent = parent
        self.span_id = span_id

    def get(self) -> model.TraceSpan | None:
        """Get the span details.

        Returns:
            TraceSpan model instance or None if not found
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

        return model.TraceSpan.from_storage(record)
