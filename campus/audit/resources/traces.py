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


def _build_span_tree(spans: list[dict]) -> dict | None:
    """Build a hierarchical tree from flat span list.

    Args:
        spans: Flat list of span records from storage

    Returns:
        Root span with nested children, or None if no spans
    """
    if not spans:
        return None

    # Build span map for O(1) lookup
    span_map = {s["span_id"]: {**s, "children": []} for s in spans}

    # Find root and organize children
    root = None
    for span in spans:
        span_id = span["span_id"]
        parent_id = span.get("parent_span_id")
        if parent_id is None:
            root = span_map[span_id]
        elif parent_id in span_map:
            span_map[parent_id]["children"].append(span_map[span_id])

    # Calculate tree metrics (depth, offset)
    if root:
        _calculate_tree_metrics(root, 0, 0)

    return root


def _calculate_tree_metrics(span: dict, depth: int, offset: float) -> float:
    """Calculate depth and offset for each span in tree.

    Args:
        span: Span node with children
        depth: Current depth in tree
        offset: Current offset from parent start

    Returns:
        Total duration of this span subtree
    """
    span["depth"] = depth
    span["offset"] = offset

    children_duration = 0
    for child in span.get("children", []):
        child_duration = _calculate_tree_metrics(child, depth + 1, children_duration)
        children_duration = max(children_duration, child_duration)

    return max(span.get("duration_ms", 0), children_duration)


def _build_trace_summaries(spans: list[dict]) -> list[dict]:
    """Build trace summaries from span list.

    Groups spans by trace_id and creates summary records.

    Args:
        spans: Flat list of span records

    Returns:
        List of trace summary dictionaries
    """
    # Group spans by trace_id
    traces: dict[str, list[dict]] = {}
    for span in spans:
        trace_id = span["trace_id"]
        if trace_id not in traces:
            traces[trace_id] = []
        traces[trace_id].append(span)

    # Build summaries
    summaries = []
    for trace_id, trace_spans in traces.items():
        root_span = next((s for s in trace_spans if s.get("parent_span_id") is None), None)
        if root_span:
            summaries.append({
                "trace_id": trace_id,
                "span_count": len(trace_spans),
                "started_at": root_span["started_at"],
                "duration_ms": root_span["duration_ms"],
                "root_span": model.TraceSpan.from_storage(root_span),
            })
        else:
            # No root span, use earliest span
            earliest = min(trace_spans, key=lambda s: s["started_at"])
            summaries.append({
                "trace_id": trace_id,
                "span_count": len(trace_spans),
                "started_at": earliest["started_at"],
                "duration_ms": sum(s.get("duration_ms", 0) for s in trace_spans),
                "root_span": model.TraceSpan.from_storage(earliest),
            })

    return summaries


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
    ) -> "list[dict]":
        """List traces newest first with optional time range filter.

        Args:
            since: ISO 8601 timestamp (optional)
            until: ISO 8601 timestamp (optional)
            limit: Maximum number of traces to return

        Returns:
            List of trace summary dictionaries
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
    ) -> "list[dict]":
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
            List of trace summary dictionaries
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

    Maps to URL path: /traces/{trace_id}
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

    def get_tree(self) -> dict | None:
        """Get full trace tree with nested children.

        Returns:
            Root span with nested children array, or None if not found
        """
        try:
            spans = traces_storage.get_matching({"trace_id": self.trace_id})
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e)

        return _build_span_tree(spans)

    def get(self) -> dict | None:
        """Get trace summary (alias for get_tree).

        Returns:
            Trace tree or None
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

        Maps to URL path: /traces/{trace_id}/spans/{span_id}

        Args:
            span_id: The 16-char hex span identifier

        Returns:
            SpanResource instance
        """
        return SpanResource(self, span_id)

    def list(self) -> "list[model.TraceSpan]":
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
