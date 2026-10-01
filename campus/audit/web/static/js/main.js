/* Campus Audit Web UI - shared helpers (issue #429) */

/**
 * Escape text for safe insertion via innerHTML.
 */
function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value === null || value === undefined ? '' : String(value);
    return div.innerHTML;
}

/**
 * Map an HTTP status code to a badge CSS class.
 */
function statusBadgeClass(statusCode) {
    if (statusCode === null || statusCode === undefined) {
        return 'pending';
    }
    if (statusCode < 300) {
        return 'ok';
    }
    if (statusCode < 400) {
        return 'redirect';
    }
    if (statusCode < 500) {
        return 'client-error';
    }
    return 'server-error';
}

/**
 * Render an HTTP status code as a badge element.
 */
function renderStatusBadge(statusCode) {
    const label = statusCode === null || statusCode === undefined ? '—' : String(statusCode);
    return `<span class="status-badge ${statusBadgeClass(statusCode)}">${label}</span>`;
}

/**
 * Format a duration in milliseconds for display.
 */
function formatDuration(durationMs) {
    if (durationMs === null || durationMs === undefined) {
        return '—';
    }
    if (durationMs >= 1000) {
        return `${(durationMs / 1000).toFixed(2)} s`;
    }
    return `${Number(durationMs).toFixed(1)} ms`;
}

/**
 * Fetch JSON from the audit API and return the parsed body.
 * Throws an Error with a readable message on non-2xx responses.
 */
async function fetchJson(url) {
    const response = await fetch(url, {headers: {'Accept': 'application/json'}});
    if (!response.ok) {
        throw new Error(`Request failed (${response.status} ${response.statusText})`);
    }
    return response.json();
}
