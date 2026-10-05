"""Unit tests for audit web UI client-name resolution (#820).

Pure logic tests: the resolver's cache behaviour (with the network
fetch stubbed) and the span-dict enrichment helpers. No storage, no
network.
"""

import unittest
from unittest import mock

from campus.audit.web import clientnames


def _reset_cache():
    clientnames._names = {}
    clientnames._fetched_at = None


class TestGetClientNames(unittest.TestCase):
    """get_client_names() caches and degrades gracefully."""

    def setUp(self):
        _reset_cache()
        self.addCleanup(_reset_cache)

    def test_resolves_known_ids_omits_unknown(self):
        fetch = mock.Mock(return_value={"c1": "Classroom", "c2": "API"})
        with mock.patch.object(clientnames, "_fetch_client_names", fetch):
            names = clientnames.get_client_names(["c1", "c2", "gone"])

        self.assertEqual(names, {"c1": "Classroom", "c2": "API"})
        fetch.assert_called_once()

    def test_cached_within_ttl(self):
        fetch = mock.Mock(return_value={"c1": "Classroom"})
        with mock.patch.object(clientnames, "_fetch_client_names", fetch):
            clientnames.get_client_names(["c1"])
            clientnames.get_client_names(["c1"])

        fetch.assert_called_once()

    def test_refetches_after_ttl(self):
        fetch = mock.Mock(return_value={"c1": "Classroom"})
        with mock.patch.object(clientnames, "_fetch_client_names", fetch):
            clientnames.get_client_names(["c1"])
            clientnames._fetched_at -= clientnames._CACHE_TTL_SECONDS + 1
            clientnames.get_client_names(["c1"])

        self.assertEqual(fetch.call_count, 2)

    def test_failure_keeps_previous_map(self):
        """A failed refresh keeps serving the last good map."""
        responses = iter([{"c1": "Classroom"}])

        def flaky_fetch():
            try:
                return next(responses)
            except StopIteration:
                raise RuntimeError("auth down") from None

        with mock.patch.object(clientnames, "_fetch_client_names", flaky_fetch):
            self.assertEqual(
                clientnames.get_client_names(["c1"]),
                {"c1": "Classroom"},
            )
            clientnames._fetched_at -= clientnames._CACHE_TTL_SECONDS + 1
            self.assertEqual(
                clientnames.get_client_names(["c1"]),
                {"c1": "Classroom"},
            )

    def test_failure_with_no_cache_returns_empty(self):
        def broken_fetch():
            raise RuntimeError("auth down")

        with mock.patch.object(clientnames, "_fetch_client_names", broken_fetch):
            self.assertEqual(clientnames.get_client_names(["c1"]), {})

    def test_empty_input_skips_fetch(self):
        fetch = mock.Mock()
        with mock.patch.object(clientnames, "_fetch_client_names", fetch):
            self.assertEqual(clientnames.get_client_names([]), {})
            self.assertEqual(clientnames.get_client_names([""]), {})

        fetch.assert_not_called()


class TestEnrichment(unittest.TestCase):
    """enrich_summaries()/enrich_tree() attach resolved names."""

    def setUp(self):
        _reset_cache()
        self.addCleanup(_reset_cache)

    def _patch_resolver(self):
        return mock.patch.object(
            clientnames,
            "get_client_names",
            mock.Mock(return_value={"c1": "Classroom"}),
        )

    def test_summary_roots_get_client_name(self):
        traces = [
            {"trace_id": "t1", "root_span": {"client_id": "c1"}},
            {"trace_id": "t2", "root_span": {"client_id": "gone"}},
            {"trace_id": "t3", "root_span": {}},
        ]
        with self._patch_resolver():
            clientnames.enrich_summaries(traces)

        self.assertEqual(traces[0]["root_span"]["client_name"], "Classroom")
        self.assertNotIn("client_name", traces[1]["root_span"])
        self.assertNotIn("client_name", traces[2]["root_span"])

    def test_tree_enrichment_reaches_children(self):
        tree = {
            "client_id": "c1",
            "children": [
                {"client_id": "c1", "children": []},
                {"children": [{"client_id": "gone"}]},
            ],
        }
        with self._patch_resolver():
            clientnames.enrich_tree(tree)

        self.assertEqual(tree["client_name"], "Classroom")
        self.assertEqual(tree["children"][0]["client_name"], "Classroom")
        self.assertNotIn("client_name", tree["children"][1]["children"][0])

    def test_no_ids_means_no_fetch(self):
        """Enrichment without client ids never touches the network."""
        fetch = mock.Mock()
        with mock.patch.object(clientnames, "_fetch_client_names", fetch):
            clientnames.enrich_summaries([{"root_span": {}}])
            clientnames.enrich_tree({"children": []})

        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
