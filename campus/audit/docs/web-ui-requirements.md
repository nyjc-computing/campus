# Audit Web UI Requirements

**Document Version:** 1.1
**Date:** 2026-04-16 (updated 2026-10-02: landing page, login page, dense table)
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

| Page | Path | Purpose | Access |
|------|------|---------|--------|
| Landing | `/audit/` | Service intro; links to the trace list and login | Public |
| Trace List | `/audit/traces` | Browse and filter traces | Login required |
| Trace Detail | `/audit/traces/<trace_id>` | View waterfall and span details | Login required |
| Login | `/audit/login` | Sign-in page (button starts the OAuth flow) | Public |
| (Future) Metrics | `/audit/metrics` | Performance dashboards | Login required |

> **Changed (2026-10):** the trace list moved from `/audit/` to
> `/audit/traces` when the public landing page was added; `/audit/login`
> became a real page (its button starts the flow at
> `/audit/login/start`), and logout redirects back to the landing page.

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
| Trace ID | Clickable link to detail page | Monospace, full ID on one line (no wrap; table scrolls horizontally) |
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

> **Implemented (2026-10, #696).** This section describes the shipped
> design, which differs from the original draft: the token is held in a
> server-side signed cookie session (never in localStorage), and the
> browser never sees or sends a Bearer token — data endpoints are
> served by the audit service itself under `/audit/api/*` and authorized
> by the session cookie. Reference implementation:
> `campus/audit/web/auth.py`. The login chain it drives is documented
> in [auth-login-flow.md](../../../docs/auth-login-flow.md).

### 5.1 Authentication Method

**Browser OAuth flow via Campus Auth (authorization-code grant):**

1. Unauthenticated access to any gated `/audit/*` page redirects to
   `/audit/login`, which renders a login page. Its button starts the
   flow at `/audit/login/start` (the landing page at `/audit/` and the
   UI's static assets are public and skip the gate).
2. `/audit/login/start` creates a Campus auth session server-to-server
   (`POST /auth/v1/sessions/campus/`) and redirects the browser to
   Campus Auth `GET /auth/v1/authorize` with the session id as the
   OAuth `state`.
3. Campus Auth authenticates the user (Google Workspace) and redirects
   back to `GET /audit/callback?code=...&state=...`.
4. `/audit/callback` validates `state` (CSRF), exchanges the code at
   `POST /auth/v1/token` (confidential client: `client_id` +
   `client_secret`, server-to-server), and stores the token and user
   identity in the signed Flask cookie session. The token is never
   exposed to browser JS; the browser is then sent to the trace list.
5. Subsequent requests are authorized by the session cookie.
6. `/audit/logout` revokes the token (RFC 7009, best-effort), clears
   the session, and redirects to the landing page.

The gate **fails closed**: if `AUDIT_OAUTH_CLIENT_ID` /
`AUDIT_OAUTH_CLIENT_SECRET` are not configured, gated UI pages return
503 and `/audit/api/*` returns 401 — the UI is never silently open.

**Protected Routes:**
- All `/audit/*` UI pages require authentication
- Exceptions: the landing page `/audit/`, the UI's static assets
  (needed by the public pages), and `/audit/v1/health`;
  `/audit/v1/*` keeps its API-key authentication (unchanged)

### 5.2 Authorization

**Access Control:**
- Only authenticated users can view traces
- Users can only view traces from clients they have access to (enforced by API)
- Admin users can view all traces (future enhancement)

---

## 6. API Integration

> **Implemented (2026-10, #429/#696).** The browser fetches from the
> audit service's own session-authenticated data endpoints
> (`/audit/api/*`), not the API-key-authed versioned API — the browser
> holds no API key and no Bearer token (see §5).

### 6.1 Endpoints Used

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /audit/api/traces` | List traces with filters (session cookie) | `{"traces": [...], "cursor": {...}}` |
| `GET /audit/api/traces/<trace_id>` | Get trace tree (session cookie) | Trace object with nested spans |
| `GET /audit/api/traces/<trace_id>/spans/<span_id>` | Get span details (session cookie) | Full span with headers/bodies |

The versioned API (`GET /audit/v1/traces` etc.) remains available to
server-side callers with an audit API key and is not used by the
browser.

### 6.2 Request Headers

Data requests carry the login session cookie automatically
(same-origin `fetch`); no `Authorization` header is involved.

### 6.3 Error Handling

| Status | Action |
|--------|--------|
| 401 Unauthorized | Redirect to login (the gate does this server-side before pages render) |
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
- **Display:** Full trace ID in list tables, on one line without
  wrapping (dense table, horizontal scroll); full on detail pages.
  (Until 2026-10 the list truncated to the first 8 chars.)
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

- [x] Trace list loads and displays recent traces
- [x] Filters work (path, status, time range, client_id, user_id)
      — path/status/time-range filters are wired; client_id/user_id
      display in the table but are not yet filterable (data endpoint
      passes only path/status/since/until; resource layer already
      supports them)
- [x] Trace detail shows waterfall correctly
- [x] Clicking span shows full headers/bodies
- [x] Tracebacks display formatted when present
- [x] Manual browser testing passes
- [x] OAuth login flow works (#696, verified on dev 2026-10)
- [x] UI is responsive on mobile devices
