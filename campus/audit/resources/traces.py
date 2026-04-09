"""campus.audit.resources.traces

Trace span resource for Campus audit service.

URL path mapping:
    /traces                     → TracesResource (list, search, ingest)
    /traces/{trace_id}          → TraceResource (get_tree)
    /traces/{trace_id}/spans    → TraceSpansResource (list)
    /traces/{trace_id}/spans/{span_id} → SpanResource (get)
"""

__all__ = []

import typing

from campus.common.errors import api_errors
import campus.model as model
import campus.storage

traces_storage = campus.storage.tables.get_db("spans")


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


class TracesResource:
    """Represents the traces resource in Campus audit API."""

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
        limit: int = 50,
    ) -> list[model.TraceSummary]:
        """List traces newest first with optional time range filter.

        Args:
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Maximum number of traces to return

        Returns:
            List of TraceSummary model instances
        """
        query = {}
        if since:
            query["started_at"] = campus.storage.gte(since)
        if until:
            query["started_at"] = campus.storage.lte(until)

        try:
            spans = traces_storage.get_matching(
                query,
                order_by="started_at",
                ascending=False,
                limit=limit * 10,  # Get more spans to find unique traces
            )
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e)

        return _build_trace_summaries(spans)[:limit]

    def search(
        self,
        path: str | None = None,
        status: int | None = None,
        api_key_id: str | None = None,
        client_id: str | None = None,
        user_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
    ) -> typing.List[model.TraceSummary]:
        """Search traces by multiple filter criteria.

        Args:
            path: Filter by endpoint path
            status: Filter by HTTP status code
            api_key_id: Filter by API key
            client_id: Filter by OAuth client
            user_id: Filter by user
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Maximum number of traces to return

        Returns:
            List of TraceSummary model instances
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
        if since:
            query["started_at"] = campus.storage.gte(since)
        if until:
            # Combine time range filters
            if "started_at" in query:
                # Both since and until - need to handle differently
                # For now, just use the most recent filter
                pass
            query["started_at"] = campus.storage.lte(until)

        try:
            spans = traces_storage.get_matching(
                query,
                order_by="started_at",
                ascending=False,
                limit=limit * 10,
            )
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e)

        return _build_trace_summaries(spans)[:limit]


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
            raise api_errors.InternalError.from_exception(e)

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
            raise api_errors.InternalError.from_exception(e)

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
            raise api_errors.InternalError.from_exception(e)

        # Verify it belongs to this trace
        if record.get("trace_id") != self._parent._parent.trace_id:
            return None

        return model.TraceSpan.from_storage(record)
