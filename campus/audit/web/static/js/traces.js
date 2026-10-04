/* Campus Audit Web UI - trace list page (issues #429, #698) */

(function () {
    'use strict';

    const form = document.getElementById('trace-filters');
    const tableBody = document.getElementById('trace-table-body');
    const statusRegion = document.getElementById('list-status');
    const loadMoreBtn = document.getElementById('load-more');

    // UI data endpoint (served in-process). The versioned API requires an
    // API key the browser cannot hold, so it must not be called from here.
    const SEARCH_URL = '/audit/api/traces';

    // Cursor pagination state: token of the last loaded page. Reset on
    // any fresh (filter-driven) load.
    const state = {
        cursor: null,
        hasMore: false,
    };

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

    function setStatus(message, isError) {
        statusRegion.innerHTML = message
            ? `<span class="${isError ? 'error' : ''}">${escapeHtml(message)}</span>`
            : '';
    }

    function updateLoadMore() {
        loadMoreBtn.hidden = !state.hasMore;
        loadMoreBtn.disabled = false;
        loadMoreBtn.textContent = 'Load more';
    }

    async function loadNextPage() {
        try {
            const params = readFilters();
            if (state.cursor) {
                params.set('cursor', state.cursor);
            }
            const data = await fetchJson(`${SEARCH_URL}?${params.toString()}`);
            const traces = data.traces || [];
            tableBody.insertAdjacentHTML('beforeend', traces.map(renderTraceRow).join(''));
            state.cursor = (data.cursor && data.cursor.next) || null;
            state.hasMore = Boolean(data.cursor && data.cursor.has_more && state.cursor);
            const total = tableBody.rows.length;
            if (total === 0) {
                setStatus('No traces match the current filters.', false);
            } else {
                setStatus(`Showing ${total} trace${total === 1 ? '' : 's'}.`, false);
            }
        } catch (err) {
            state.cursor = null;
            state.hasMore = false;
            setStatus(`Failed to load traces: ${err.message}`, true);
        }
        updateLoadMore();
    }

    function loadTraces() {
        tableBody.innerHTML = '';
        state.cursor = null;
        state.hasMore = false;
        loadMoreBtn.hidden = true;
        setStatus('Loading traces…', false);
        loadNextPage();
    }

    loadMoreBtn.addEventListener('click', () => {
        loadMoreBtn.disabled = true;
        loadMoreBtn.textContent = 'Loading…';
        loadNextPage();
    });

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
