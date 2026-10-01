/* Campus Audit Web UI - trace list page (issue #429) */

(function () {
    'use strict';

    const form = document.getElementById('trace-filters');
    const tableBody = document.getElementById('trace-table-body');
    const statusRegion = document.getElementById('list-status');

    // UI data endpoint (served in-process). The versioned API requires an
    // API key the browser cannot hold, so it must not be called from here.
    const SEARCH_URL = '/audit/api/traces';

    function readFilters() {
        const params = new URLSearchParams();
        const fields = form.elements;
        for (const field of fields) {
            if (!field.name || !field.value) {
                continue;
            }
            params.set(field.name, field.value);
        }
        return params;
    }

    function renderRow(summary) {
        const root = summary.root_span || {};
        const detailHref = `/audit/traces/${encodeURIComponent(summary.trace_id)}`;
        const client = root.client_id || '—';
        const user = root.user_id || '—';
        return `
            <tr>
                <td class="wrap" title="${escapeHtml(summary.trace_id)}"><a href="${detailHref}">${escapeHtml(formatTraceId(summary.trace_id))}</a></td>
                <td title="${escapeHtml(summary.started_at || '')}">${escapeHtml(formatTimestamp(summary.started_at))}</td>
                <td>${escapeHtml(root.method || '—')}</td>
                <td class="wrap">${escapeHtml(root.path || '—')}</td>
                <td>${renderStatusBadge(root.status_code)}</td>
                <td>${escapeHtml(formatDuration(summary.duration_ms))}</td>
                <td>${escapeHtml(summary.span_count)}</td>
                <td class="wrap">${escapeHtml(client)}</td>
                <td class="wrap">${escapeHtml(user)}</td>
            </tr>`;
    }

    function setStatus(message, isError) {
        statusRegion.innerHTML = message
            ? `<span class="${isError ? 'error' : ''}">${escapeHtml(message)}</span>`
            : '';
    }

    async function loadTraces() {
        tableBody.innerHTML = '';
        setStatus('Loading traces…', false);
        try {
            const params = readFilters();
            const data = await fetchJson(`${SEARCH_URL}?${params.toString()}`);
            const traces = data.traces || [];
            if (traces.length === 0) {
                setStatus('No traces match the current filters.', false);
                return;
            }
            tableBody.innerHTML = traces.map(renderRow).join('');
            let summary = `Showing ${traces.length} trace${traces.length === 1 ? '' : 's'}.`;
            if (data.cursor && data.cursor.has_more) {
                // The API does not return a usable cursor yet (always null);
                // surface it honestly instead of pretending we can paginate.
                summary += ' More results exist but pagination is not yet available.';
            }
            setStatus(summary, false);
        } catch (err) {
            setStatus(`Failed to load traces: ${err.message}`, true);
        }
    }

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        loadTraces();
    });

    form.addEventListener('reset', () => {
        // Let the browser clear the fields, then reload unfiltered.
        window.setTimeout(loadTraces, 0);
    });

    loadTraces();
})();
