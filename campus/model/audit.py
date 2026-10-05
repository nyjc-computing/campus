"""campus.model.audit

Audit-related models for Campus API.

These models represent trace spans and computed views/aggregations
for the audit service, including trace trees and summaries.
"""

import datetime
import typing
from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import uid, utc_time
from campus.model.base import InternalModel, Model

__all__ = [
    "APIKey",
    "TraceSpan",
    "TraceTreeNode",
    "TraceTree",
    "TraceSummary",
]

# Fallback for span records with an unparseable started_at: sorts before
# every real timestamp (all Campus timestamps are tz-aware UTC), so such
# spans become the tree root rather than disappearing.
_EPOCH_FALLBACK = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def _parse_started_at(span: dict) -> datetime.datetime | None:
    """Parse a span record's started_at into an aware UTC datetime.

    Storage records carry the ISO string; in-memory dicts may already
    hold a schema.DateTime (a str subclass).
    """
    value = span.get("started_at")
    if isinstance(value, schema.DateTime):
        return value.to_datetime()
    try:
        return schema.DateTime(str(value)).to_datetime()
    except (TypeError, ValueError):
        return None


def _span_start_key(span: dict) -> tuple[datetime.datetime, str]:
    """Deterministic sort key for spans: (started_at, span_id)."""
    parsed = _parse_started_at(span)
    return (
        parsed if parsed is not None else _EPOCH_FALLBACK,
        str(span.get("span_id") or ""),
    )


@dataclass(eq=False, kw_only=True)
class APIKey(Model):
    """An API key issued for the campus.audit service.

    Only the key hash is stored; the plaintext value is shown once at
    creation and never persisted. Lifecycle is tracked through
    expires_at/revoked_at, and access is scoped via the scopes list
    (e.g. "traces:read", "traces:*").

    Issue: #566
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("apikey", length=16)
    ))
    # created_at: schema.DateTime is inherited from Model
    # key_hash is stored in place of plaintext key for security
    # and is not exposed via API resources
    key_hash: schema.String = field(metadata={"resource": False})
    name: schema.String
    owner_id: schema.UserID
    scopes: list[schema.String] = field(default_factory=list)
    # expires_at, revoked_at, and last_used are immutable audit fields
    # They can be set through internal resource but not via the API.
    expires_at: schema.DateTime | None = field(
        default=None,
        metadata={"mutable": False}
    )
    revoked_at: schema.DateTime | None = field(
        default=None,
        metadata={"mutable": False}
    )
    last_used: schema.DateTime | None = field(
        default=None,
        metadata={"mutable": False}
    )
    # Requests per minute, None for unlimited
    rate_limit: schema.Integer | None = None

    def is_active(self) -> bool:
        """Check if the API key is currently active (not expired or
        revoked).
        
        Returns:
            bool: True if the API key is active, False otherwise.
        """
        return not self.is_expired() and not self.is_revoked()

    def is_expired(self) -> bool:
        """Check if the API key is expired.

        A key with no expires_at never expires.

        Returns:
            bool: True if the API key is expired, False otherwise.
        """
        if self.expires_at is None:
            return False
        # Storage records carry plain strings for union-annotated
        # fields (from_storage only coerces single-class annotations)
        expires_at = self.expires_at
        if isinstance(expires_at, str):
            expires_at = schema.DateTime(expires_at)
        return expires_at.to_datetime() < utc_time.now()

    def is_revoked(self) -> bool:
        """Check if the API key is revoked.

        Returns:
            bool: True if the API key is revoked, False otherwise.
        """
        return self.revoked_at is not None

    def has_scope(self, scope: str) -> bool:
        """Check if the API key has a specific scope.

        Matching is exact: wildcard scopes stored on the key (e.g.
        "traces:*", "*") only match themselves. Wildcard expansion is
        the authorization layer's responsibility (#575).

        Args:
            scope (str): The scope to check for.

        Returns:
            bool: True if the API key has the scope, False otherwise.

        Raises:
            TypeError: If the scope is not a string.
        """
        if not isinstance(scope, str):
            raise TypeError(
                f"Scope must be a string, got {type(scope).__name__}"
            )
        return scope in self.scopes

    @classmethod
    def validate_update(cls, update: dict[str, typing.Any]) -> None:
        """Validate an update dictionary against the APIKey model.

        Extends the base mutability check with type validation for the
        mutable fields.

        Args:
            update: Dictionary of fields to update

        Raises:
            ValueError: If any field is not mutable or has an invalid
                value.
        """
        super().validate_update(update)
        if "scopes" in update:
            scopes = update["scopes"]
            if not isinstance(scopes, list) or not all(
                    isinstance(s, str) for s in scopes
            ):
                raise ValueError(
                    "scopes must be a list of scope strings"
                )
        if "rate_limit" in update:
            rate_limit = update["rate_limit"]
            if rate_limit is not None and (
                    isinstance(rate_limit, bool) or not isinstance(rate_limit, int)
            ):
                raise ValueError(
                    "rate_limit must be an integer or None"
                )


@dataclass(eq=False, kw_only=True)
class TraceSpan(InternalModel):
    """A single span in a distributed trace.

    Captures HTTP request-response data for observability and debugging.
    Uses OpenTelemetry-compatible trace/span ID formats.

    Note: The `id` field is a Campus storage convention that mirrors `span_id`.
    The `span_id` field follows OpenTelemetry conventions (16-char hex).

    Attributes:
        id: Alias for span_id (Campus storage convention, stored as 'id' column)
        trace_id: 32-char hex string grouping related spans
        span_id: 16-char hex string identifying this span (OpenTelemetry convention)
        parent_span_id: 16-char hex string of parent span, null for roots
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g. /api/v1/students)
        query_params: Query string parameters as dict
        request_headers: Request headers (Authorization stripped)
        request_body: Request body JSON (if applicable)
        status_code: HTTP response status code
        response_headers: Response headers
        response_body: Response body JSON (truncated to 64KB)
        started_at: Span start timestamp
        duration_ms: Span duration in milliseconds
        api_key_id: API key used for the request
        client_id: OAuth client identifier (null until auth succeeds)
        user_id: User identifier (null until auth succeeds)
        client_ip: Client IP address
        user_agent: User-Agent header value
        error_message: Error details for failed requests
        tags: Arbitrary key-value metadata
    """

    # Trace identification (OpenTelemetry-compatible)
    id: str = field(
        default="",
        metadata={"resource": False}  # Hide from API, use as PK only
    )
    trace_id: str = field(default_factory=uid.generate_trace_id)  # 32-char hex
    # 16-char hex (OpenTelemetry identifier, used in resources)
    span_id: str = field(default_factory=uid.generate_span_id)
    parent_span_id: str | None = None

    # Request data
    method: str  # HTTP method
    path: str  # Request path
    query_params: dict[str, object] = field(default_factory=dict)
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: dict[str, object] | None = None

    # Response data
    status_code: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: dict[str, object] | None = None

    # Timing
    started_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)
    duration_ms: float  # milliseconds

    # Identity (nullable - populated after auth)
    api_key_id: str | None = None
    client_id: str | None = None
    user_id: str | None = None

    # Client info
    client_ip: str  # INET type
    user_agent: str | None = None

    # Error info
    error_message: str | None = None

    # Metadata
    tags: dict[str, object] = field(default_factory=dict)

    def __post_init__(self):
        """Alias id to span_id after initialization.

        This ensures the Campus storage convention (id field as PK)
        aligns with OpenTelemetry convention (span_id as identifier).
        """
        if self.id == "" or self.id is None:
            # Use object.__setattr__ to avoid frozen dataclass issues
            object.__setattr__(self, "id", self.span_id)


@dataclass(eq=False, kw_only=True)
class TraceTreeNode(InternalModel):
    """A node in a trace tree hierarchy.

    Represents a span with its children and tree metrics.
    Computed from storage, not stored directly.

    Attributes:
        span_id: 16-char hex span identifier
        trace_id: 32-char hex trace identifier
        parent_span_id: Parent span ID, None for root
        method: HTTP method
        path: Request path
        status_code: HTTP response status
        started_at: Span start timestamp
        duration_ms: Span duration in milliseconds
        error_message: Error details if applicable
        children: Nested child spans
        depth: Depth in tree (0 for root)
        offset: Offset from parent start for visualization
    """

    # Span data (from TraceSpan)
    span_id: str
    trace_id: str
    parent_span_id: str | None
    method: str
    path: str
    status_code: int | None
    started_at: schema.DateTime
    duration_ms: float
    error_message: str | None

    # Identity (#823): the summary path exposes these via the full
    # TraceSpan; the tree path must too, or the detail page and the
    # versioned detail API disagree with the list on the same spans.
    client_id: str | None = None
    user_id: str | None = None

    # Tree structure
    children: "list[TraceTreeNode]" = field(default_factory=list)

    # Tree metrics (computed)
    depth: int = 0
    offset: float = 0.0

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert to resource dictionary for JSON response.

        Returns:
            Dictionary with nested children arrays
        """
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "started_at": self.started_at,  # DateTime is already a string
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "client_id": self.client_id,
            "user_id": self.user_id,
            "children": [child.to_resource() for child in self.children],
            "depth": self.depth,
            "offset": self.offset,
        }

    @classmethod
    def from_storage(cls: type[typing.Self], record: dict[str, typing.Any]) -> typing.Self:
        """TraceTreeNode is computed, not stored. Use TraceTree.from_spans() instead."""
        _ = record  # Unused - computed view, not stored
        raise NotImplementedError(
            "TraceTreeNode is computed from spans, not loaded from storage. "
            "Use TraceTree.from_spans() to build trace trees."
        )

    def to_storage(self) -> dict[str, typing.Any]:
        """TraceTreeNode is computed, not stored."""
        raise NotImplementedError(
            "TraceTreeNode is a computed view and cannot be stored."
        )

    @classmethod
    def from_resource(cls: type[typing.Self], resource: dict[str, typing.Any]) -> typing.Self:
        """TraceTreeNode is computed from spans, not created from resources."""
        _ = resource  # Unused - computed view, not from resources
        raise NotImplementedError(
            "TraceTreeNode is computed from spans, not created from API resources. "
            "Use TraceTree.from_spans() to build trace trees."
        )


@dataclass(eq=False, kw_only=True)
class TraceTree(InternalModel):
    """A hierarchical trace tree with computed metrics.

    Represents a complete trace with all spans organized
    in a tree structure with depth and offset metrics.

    Attributes:
        root: Root span node with nested children, or None if empty
    """

    root: TraceTreeNode | None

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert to resource dictionary for JSON response.

        Returns:
            Root span dict with nested children, or empty dict if no root
        """
        if self.root is None:
            return {}
        return self.root.to_resource()

    @classmethod
    def from_spans(cls: type[typing.Self], spans: list[dict]) -> typing.Self:
        """Build a trace tree from flat span list.

        The root is the earliest-started span without a parent. Spans
        whose parent was not ingested (or additional root spans, which
        can appear in traces assembled from propagated X-Request-IDs)
        are adopted under the root, ordered by started_at, so every
        span stays visible in the waterfall (#794).

        Args:
            spans: Flat list of span records from storage

        Returns:
            TraceTree instance with root or None
        """
        if not spans:
            return cls(root=None)

        # Build span map for O(1) lookup
        span_map: dict[str, dict] = {s["span_id"]: {**s, "children": []} for s in spans}

        # Wire children to parents; collect spans with no parent in the
        # set (root spans, or orphans whose parent is missing) as tops.
        tops: list[dict] = []
        for span in spans:
            node = span_map[span["span_id"]]
            parent_id = span.get("parent_span_id")
            if parent_id is None or parent_id == span["span_id"]:
                # Root span (normalize self-parenting, which would cycle)
                node["parent_span_id"] = None
                tops.append(node)
            elif parent_id in span_map:
                span_map[parent_id]["children"].append(node)
            else:
                # Orphan: parent span not ingested; adopt under the root
                node["parent_span_id"] = None
                tops.append(node)

        if not tops:
            # Defensive: every span is somebody's child, which requires a
            # parent cycle. Break it at the earliest span.
            earliest = min(span_map.values(), key=_span_start_key)
            parent_id = earliest.get("parent_span_id")
            earliest["parent_span_id"] = None
            if parent_id in span_map:
                siblings = span_map[parent_id]["children"]
                siblings[:] = [
                    s for s in siblings if s["span_id"] != earliest["span_id"]
                ]
            tops = [earliest]

        tops.sort(key=_span_start_key)
        root_dict = tops[0]
        root_dict["children"].extend(tops[1:])
        root_dict["children"].sort(key=_span_start_key)
        root = cls._build_node(root_dict, 0, 0.0)

        return cls(root=root)

    @classmethod
    def _build_node(
        cls,
        span_dict: dict,
        depth: int,
        offset: float,
    ) -> TraceTreeNode:
        """Build a TraceTreeNode from span dict with children.

        Args:
            span_dict: Span dict with children array
            depth: Current depth in tree
            offset: Offset from parent start in ms

        Returns:
            TraceTreeNode with nested children
        """
        parent_start = _parse_started_at(span_dict)
        child_nodes: list[TraceTreeNode] = []

        for child_dict in span_dict.get("children", []):
            child_start = _parse_started_at(child_dict)
            if parent_start is not None and child_start is not None:
                child_offset = max(0.0, (child_start - parent_start).total_seconds() * 1000)
            else:
                child_offset = 0.0
            child = cls._build_node(child_dict, depth + 1, child_offset)
            child_nodes.append(child)

        node = TraceTreeNode(
            span_id=span_dict["span_id"],
            trace_id=span_dict["trace_id"],
            parent_span_id=span_dict.get("parent_span_id"),
            method=span_dict["method"],
            path=span_dict["path"],
            status_code=span_dict.get("status_code"),
            started_at=span_dict["started_at"],
            duration_ms=span_dict.get("duration_ms", 0),
            error_message=span_dict.get("error_message"),
            client_id=span_dict.get("client_id"),
            user_id=span_dict.get("user_id"),
            children=child_nodes,
            depth=depth,
            offset=offset,
        )

        return node

    @classmethod
    def from_storage(cls: type[typing.Self], record: dict[str, typing.Any]) -> typing.Self:
        """TraceTree is computed, not stored. Use TraceTree.from_spans() instead."""
        _ = record  # Unused - computed view, not stored
        raise NotImplementedError(
            "TraceTree is computed from spans, not loaded from storage. "
            "Use TraceTree.from_spans(spans) to build trace trees."
        )

    def to_storage(self) -> dict[str, typing.Any]:
        """TraceTree is computed, not stored."""
        raise NotImplementedError(
            "TraceTree is a computed view and cannot be stored."
        )

    @classmethod
    def from_resource(cls: type[typing.Self], resource: dict[str, typing.Any]) -> typing.Self:
        """TraceTree is computed from spans, not created from resources."""
        _ = resource  # Unused - computed view, not from resources
        raise NotImplementedError(
            "TraceTree is computed from spans, not created from API resources. "
            "Use TraceTree.from_spans(spans) to build trace trees."
        )


@dataclass(eq=False, kw_only=True)
class TraceSummary(InternalModel):
    """A summary of a trace for listing/search results.

    Computed from spans in a trace, includes root span
    and aggregate metrics.

    Attributes:
        trace_id: 32-char hex trace identifier
        span_count: Total number of spans in trace
        started_at: Root span start timestamp
        duration_ms: Root span duration
        root_span: The root span details
    """

    trace_id: str
    span_count: int
    started_at: schema.DateTime
    duration_ms: float
    root_span: TraceSpan

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert to resource dictionary for JSON response."""
        return {
            "trace_id": self.trace_id,
            "span_count": self.span_count,
            "started_at": self.started_at,  # DateTime is already a string
            "duration_ms": self.duration_ms,
            "root_span": self.root_span.to_resource(),
        }

    @classmethod
    def from_spans(cls: type[typing.Self], trace_id: str, spans: list[dict]) -> typing.Self:
        """Build a summary from spans grouped by trace_id.

        Args:
            trace_id: The trace identifier
            spans: List of span records for this trace

        Returns:
            TraceSummary instance
        """
        # Find root span (parent_span_id is None)
        root_span_dict = next(
            (s for s in spans if s.get("parent_span_id") is None),
            None
        )

        if root_span_dict:
            root_span = TraceSpan.from_storage(root_span_dict)
            duration_ms = root_span_dict["duration_ms"]
            started_at = root_span_dict["started_at"]
        else:
            # No root span, use earliest span
            root_span_dict = min(spans, key=lambda s: s["started_at"])
            root_span = TraceSpan.from_storage(root_span_dict)
            duration_ms = sum(s.get("duration_ms", 0) for s in spans)
            started_at = root_span_dict["started_at"]

        return cls(
            trace_id=trace_id,
            span_count=len(spans),
            started_at=started_at,
            duration_ms=duration_ms,
            root_span=root_span,
        )

    @classmethod
    def from_storage(cls: type[typing.Self], record: dict[str, typing.Any]) -> typing.Self:
        """TraceSummary is computed, not stored. Use TraceSummary.from_spans() instead."""
        _ = record  # Unused - computed view, not stored
        raise NotImplementedError(
            "TraceSummary is computed from spans, not loaded from storage. "
            "Use TraceSummary.from_spans(trace_id, spans) to build summaries."
        )

    def to_storage(self) -> dict[str, typing.Any]:
        """TraceSummary is computed, not stored."""
        raise NotImplementedError(
            "TraceSummary is a computed view and cannot be stored."
        )

    @classmethod
    def from_resource(cls: type[typing.Self], resource: dict[str, typing.Any]) -> typing.Self:
        """TraceSummary is computed from spans, not created from resources."""
        _ = resource  # Unused - computed view, not from resources
        raise NotImplementedError(
            "TraceSummary is computed from spans, not created from API resources. "
            "Use TraceSummary.from_spans(trace_id, spans) to build summaries."
        )
