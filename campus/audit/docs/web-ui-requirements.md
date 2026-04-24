# Audit Web UI Requirements

**Document Version:** 1.0
**Date:** 2026-04-16
**Parent Issue:** #429
**Related:** [campus-trace-api-prd-v3.md](./campus-trace-api-prd-v3.md)

---

## 1. Overview

The Audit Web UI is a browser-based dashboard for exploring API traces captured by the Campus Trace API. It enables developers and operators to visualize request flows, debug errors, and review system performance during fortnightly and quarterly reviews.

**Target Users:**
- Campus developers debugging issues
- System operators reviewing performance
- Student cohorts learning about distributed tracing

**Technology Stack:**
- Backend: Flask (Jinja2 templates)
- Frontend: Vanilla JavaScript (no framework)
- Styling: CSS
- Authentication: OAuth browser flow

---

## 2. Pages & Navigation

### 2.1 Page Structure

| Page | Path | Purpose |
|------|------|---------|
| Trace List | `/audit/` | Browse and filter traces |
| Trace Detail | `/audit/traces/<trace_id>` | View waterfall and span details |
| (Future) Metrics | `/audit/metrics` | Performance dashboards |

### 2.2 Navigation

- **Header navigation** on all pages
  - Logo/title: "Campus Audit"
  - Links: "Traces", "Metrics" (disabled/coming soon)
  - User profile/logout (when authenticated)

---

## 3. Trace List Page

### 3.1 Purpose

Browse recent traces with filtering capabilities. Primary entry point for investigating issues.

### 3.2 Filter Bar

**Time Range Presets:**
- Quick buttons: "Past hour", "Past 24h", "Past week"
- Custom date range: Since/Until datetime inputs
- Default: Past 24h

**Filter Fields:**

| Field | Type | Description | API Mapping |
|-------|------|-------------|-------------|
| Path | Text input | Filter by endpoint path (e.g., `/api/v1/students`) | `path` query param |
| Status | Dropdown | All, 2xx, 3xx, 4xx, 5xx | `status` query param |
| Client ID | Text input | Filter by OAuth client ID (also filters by deployment) | `client_id` query param |
| User ID | Text input | Filter by specific user | `user_id` query param |

**Extensibility:**
- Filter UI should be structured to allow adding new filter types without major refactoring
- Filter state management should support arbitrary query parameters

### 3.3 Trace List Table

**Columns:**

| Column | Description | Formatting |
|--------|-------------|------------|
| Trace ID | Clickable link to detail page | Monospace, truncated to first 8 chars + "..." |
| Status | HTTP status code | Color-coded badge (green/yellow/orange/red) |
| Duration | Total trace duration | In milliseconds (e.g., "142.5ms") |
| Method | HTTP method | Badge (GET, POST, etc.) |
| Path | Request path | Truncated with full path in hover tooltip |
| Client | Client ID | (derived from api_key_id or client_id) |
| User | User ID | "—" if null |
| Timestamp | Start time | ISO 8601, localized (e.g., "2026-04-16 14:32:05") |

**Interactions:**
- Clicking Trace ID navigates to trace detail page
- Row hover effect
- Sortable by timestamp (newest first by default)

### 3.4 Pagination

- Cursor-based pagination (using `cursor.next` from API)
- "Load more" button at bottom
- Display: "Showing X of Y traces"
- Infinite scroll optional for future

### 3.5 Empty States

| Scenario | Message |
|----------|---------|
| No traces match filter | "No traces found matching your filters. Try adjusting your search criteria." |
| No traces at all | "No traces recorded yet. Traces will appear here as API traffic flows through Campus." |
| Loading | "Loading traces..." with spinner |

---

## 4. Trace Detail Page

### 4.1 Purpose

Display a single trace with waterfall visualization showing all spans and their timing relationships.

### 4.2 Trace Metadata Section

**Header Information:**

| Field | Display |
|-------|---------|
| Trace ID | Full ID, copy-to-clipboard button |
| Status | Root span status badge |
| Duration | Total duration (e.g., "142.5ms") |
| Started At | ISO 8601 timestamp, localized |
| Method + Path | Root span request (e.g., "GET /api/v1/students") |
| Client ID | Client identifier or "—" |
| User ID | User identifier or "—" |

**Actions:**
- "Back to traces" button
- "Copy trace ID" button

### 4.3 Waterfall Visualization

**Layout:**
```
Timeline: 0ms    50ms   100ms   150ms   200ms
         |       |       |       |       |
GET /api/v1/students      [=======================] 200
  +POST /auth/token       [====] 200
  +GET /api/v1/db/query          [=================] 200
    +SELECT ...users              [======] 200
```

**Visual Elements:**
- **Timeline ruler** at top with millisecond marks
- **Span bars** positioned by offset (left) and duration (width)
- **Indentation** based on depth (nested children)
- **Color coding** by status:
  - 2xx: Green (#10b981)
  - 3xx: Yellow (#f59e0b)
  - 4xx: Orange (#f97316)
  - 5xx: Red (#ef4444)
- **Labels** on span bars: method, path, status code

**Interactions:**
- Hover tooltip: shows full span details (offset, duration, all headers summary)
- Click span bar: opens span details drawer (see §4.4)
- Zoom controls (optional for future): zoom in/out of timeline

**Responsive Behavior:**
- Horizontal scroll for wide waterfalls
- Collapse to list view on very small screens

### 4.4 Span Details Drawer

**Purpose:**
Show full request/response data for a single span when clicked.

**Trigger:**
- Click any span bar in waterfall

**Layout:**
- Slide-out panel from right side
- Overlay backdrop (click to close)
- Close button (×) in header

**Content Sections:**

1. **Span Summary**
   - Span ID (copyable)
   - Method + Path + Status Code
   - Duration with offset (e.g., "15.2ms (started at +0.1ms)")
   - Timestamp

2. **Request Headers**
   - Formatted as key-value table
   - Monospace font for values
   - Authorization header shown as "Bearer ***" (redacted)

3. **Request Body**
   - Pretty-printed JSON if present
   - "No body" message if null/empty
   - Syntax highlighting (basic coloring)

4. **Response Headers**
   - Formatted as key-value table
   - Monospace font

5. **Response Body**
   - Pretty-printed JSON if present
   - "No body" message if null/empty
   - Truncation notice if `_truncated: true`
   - Syntax highlighting

6. **Error Details** (if status >= 400)
   - Error message
   - **Traceback** (if present in response JSON)
     - Pretty-printed with indentation
     - Monospace font
     - Syntax highlighting for code frames
     - Expand/collapse for long tracebacks

**Responsive:**
- Full-screen drawer on mobile
- 50% width drawer on desktop (max 600px)

---

## 5. Authentication

### 5.1 Authentication Method

**Browser OAuth Flow:**
- User clicks "Login" or accesses `/audit/`
- Redirect to Campus Auth `/oauth/authorize`
- User approves access
- Redirect back to `/audit/` with authorization code
- Exchange code for access token
- Store token in localStorage (or secure httpOnly cookie)
- Include token in `Authorization: Bearer <token>` header for API requests

**Protected Routes:**
- All `/audit/*` routes require authentication
- Exception: `/audit/v1/health` (public API endpoint)

### 5.2 Authorization

**Access Control:**
- Only authenticated users can view traces
- Users can only view traces from clients they have access to (enforced by API)
- Admin users can view all traces (future enhancement)

---

## 6. API Integration

### 6.1 Endpoints Used

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /audit/v1/traces` | List traces with filters | `{"traces": [...], "cursor": {...}}` |
| `GET /audit/v1/traces/<trace_id>` | Get trace tree | Trace object with nested spans |
| `GET /audit/v1/traces/<trace_id>/spans/<span_id>` | Get span details | Full span with headers/bodies |
| `GET /audit/v1/traces/search` | Search with filters | `{"traces": [...], "cursor": {...}}` |

### 6.2 Request Headers

All authenticated requests include:
```
Authorization: Bearer <access_token>
Accept: application/json
```

### 6.3 Error Handling

| Status | Action |
|--------|--------|
| 401 Unauthorized | Redirect to login |
| 403 Forbidden | Show "Access denied" message |
| 404 Not Found | Show "Trace not found" error |
| 429 Too Many Requests | Show rate limit message with Retry-After |
| 500+ | Show generic error with retry option |

---

## 7. Data Display Conventions

### 7.1 Timestamps

- **Storage:** ISO 8601 (UTC)
- **Display:** Local timezone (browser's timezone)
- **Format:** `YYYY-MM-DD HH:MM:SS` for list, full ISO in tooltips
- **Relative time:** "2 hours ago" in tooltips (optional)

### 7.2 Durations

- **Display:** In milliseconds with 1 decimal place
- **Format:** `142.5ms`, `1.2s` (if >= 1 second)
- **Color coding:**
  - < 100ms: Green
  - 100-500ms: Yellow
  - > 500ms: Red

### 7.3 Status Codes

| Range | Color | Label |
|-------|-------|-------|
| 2xx | Green | Success |
| 3xx | Yellow | Redirect |
| 4xx | Orange | Client Error |
| 5xx | Red | Server Error |

### 7.4 IDs

- **Trace ID:** 32 hex chars
- **Span ID:** 16 hex chars
- **Display:** Truncate to first 8 chars in tables, full in detail pages
- **Font:** Monospace

---

## 8. Non-Functional Requirements

### 8.1 Performance

- Trace list page: Initial load < 2 seconds
- Trace detail page: Initial load < 1 second
- Waterfall rendering: < 500ms for 50 spans
- Span details drawer: < 300ms to open

### 8.2 Browser Support

- Modern browsers: Chrome/Edge 90+, Firefox 88+, Safari 14+
- Mobile: iOS Safari 14+, Chrome Mobile
- Graceful degradation for older browsers

### 8.3 Accessibility

- Keyboard navigation support
- ARIA labels for interactive elements
- Sufficient color contrast (WCAG AA)
- Focus indicators

### 8.4 Security

- All API requests over HTTPS
- No sensitive data in localStorage (except access token)
- Authorization headers redacted in display
- XSS prevention (sanitize user input)

---

## 9. Future Enhancements (Out of Scope)

- Metrics dashboard: throughput, latency percentiles, error rates
- Trace comparison: side-by-side view of two traces
- Export: download trace as JSON
- Trace search: full-text search across paths, headers, bodies
- Live tail: real-time trace stream
- Annotations: add notes to traces for later review
- Alerts: webhook notifications for error patterns

---

## 10. Acceptance Criteria

From issue #429:

- [ ] Trace list loads and displays recent traces
- [ ] Filters work (path, status, time range, client_id, user_id)
- [ ] Trace detail shows waterfall correctly
- [ ] Clicking span shows full headers/bodies
- [ ] Tracebacks display formatted when present
- [ ] Manual browser testing passes
- [ ] OAuth login flow works
- [ ] UI is responsive on mobile devices
