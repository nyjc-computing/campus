/* Campus Audit Web UI - login-journey grouped view (issue #803) */

(function () {
    'use strict';

    const detailRoot = document.getElementById('journey-detail');
    const tableBody = document.getElementById('trace-table-body');
    const statusRegion = document.getElementById('list-status');

    // UI data endpoint (served in-process). The versioned API requires an
    // API key the browser cannot hold, so it must not be called from here.
    const JOURNEY_URL = '/audit/api/journeys';

    const journeyId = detailRoot ? detailRoot.dataset.journeyId : null;

    function setStatus(message, isError) {
        statusRegion.innerHTML = message
            ? `<span class="${isError ? 'error' : ''}">${escapeHtml(message)}</span>`
            : '';
    }

    async function loadJourney() {
        if (!journeyId) {
            setStatus('No journey id in URL.', true);
            return;
        }
        try {
            setStatus('Loading journey…', false);
            const data = await fetchJson(
                `${JOURNEY_URL}/${encodeURIComponent(journeyId)}`
            );
            const traces = data.traces || [];
            tableBody.innerHTML = traces.map(renderTraceRow).join('');
            if (traces.length === 0) {
                setStatus('No traces found for this journey.', false);
            } else {
                setStatus(
                    `Showing ${traces.length} trace${traces.length === 1 ? '' : 's'} ` +
                    'in this journey.',
                    false
                );
            }
        } catch (err) {
            tableBody.innerHTML = '';
            setStatus(`Failed to load journey: ${err.message}`, true);
        }
    }

    loadJourney();
})();
