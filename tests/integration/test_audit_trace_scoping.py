"""Integration tests for per-key trace-read scoping (#944).

A traces:read key minted with a trace_user_id/trace_client_id bind
sees only traces its bind matches, enforced server-side on every read
surface (list, get, spans list, span get, search, journeys). Keys
without a bind (the operator/admin class) keep today's global-read
behavior. Every test is self-contained (#570).

The mint-side fail-closed rule is covered too: a key granting trace
reads without apikeys:write must carry a bind (422 otherwise).

File: tests/integration/test_audit_trace_scoping.py
Issue: #944
"""

import unittest
from contextlib import suppress

import campus.storage
from campus.common import schema
from campus.common.utils import secret, uid
from tests.integration.base import IsolatedIntegrationTestCase

USER_A = "student-a@nyjc.edu.sg"
USER_B = "student-b@nyjc.edu.sg"
CLIENT_X = "uid-client-aaaa0000"
CLIENT_Y = "uid-client-bbbb1111"
JOURNEY = "uid-journey-scoping01"


class TestAuditTraceScoping(IsolatedIntegrationTestCase):
    """Read-surface enforcement matrix for trace binds (#944)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.audit_app = cls.manager.audit_app

        # CRITICAL: lazy-init AFTER test mode is configured (see
        # AGENTS.md storage initialization order)
        from campus.audit.resources.apikeys import APIKeysResource
        from campus.audit.resources.traces import TracesResource

        APIKeysResource.init_storage()
        TracesResource.init_storage()

    def setUp(self):
        super().setUp()
        assert self.audit_app, "Audit app not initialized"
        self.client = self.audit_app.test_client()

        for table in ("apikeys", "spans"):
            storage = campus.storage.tables.get_db(table)
            with suppress(campus.storage.errors.NoChangesAppliedError):
                storage.delete_matching({})

    # ---- fixtures -------------------------------------------------

    def _insert_key(
            self,
            scopes: list[str],
            *,
            trace_user_id: str | None = None,
            trace_client_id: str | None = None,
    ) -> str:
        """Insert an API key directly; return the plaintext value."""
        raw_api_key = secret.generate_audit_api_key()
        record = {
            "id": uid.generate_category_uid("apikey", length=16),
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw_api_key),
            "name": f"Key ({','.join(scopes)})",
            "owner_id": "test-user",
            "scopes": scopes,
        }
        if trace_user_id is not None:
            record["trace_user_id"] = trace_user_id
        if trace_client_id is not None:
            record["trace_client_id"] = trace_client_id
        campus.storage.tables.get_db("apikeys").insert_one(record)
        return raw_api_key

    def _insert_span(
            self,
            *,
            trace_id: str,
            span_id: str,
            parent_span_id: str | None = None,
            user_id: str | None = None,
            client_id: str | None = None,
            journey_id: str | None = None,
    ) -> str:
        """Insert one span record; return its span_id."""
        import campus.model as model

        tags = {"test": "scoping"}
        if journey_id is not None:
            tags["journey_id"] = journey_id
        span = model.TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            method="GET",
            path="/scoping-test",
            status_code=200,
            duration_ms=1.0,
            client_ip="127.0.0.1",
            user_id=user_id,
            client_id=client_id,
            tags=tags,
        )
        campus.storage.tables.get_db("spans").insert_one(span.to_storage())
        return span_id

    def _seed_traces(self) -> dict[str, str]:
        """Seed two user-owned traces and one anonymous trace.

        Returns:
            {"a": trace_id of user A, "b": ..., "anon": ...}
        """
        trace_a = uid.generate_trace_id()
        self._insert_span(
            trace_id=trace_a, span_id=uid.generate_span_id(),
            user_id=USER_A, client_id=CLIENT_X,
        )
        trace_b = uid.generate_trace_id()
        span_b = uid.generate_span_id()
        self._insert_span(
            trace_id=trace_b, span_id=span_b,
            user_id=USER_B, client_id=CLIENT_Y,
        )
        trace_anon = uid.generate_trace_id()
        self._insert_span(trace_id=trace_anon, span_id=uid.generate_span_id())
        return {"a": trace_a, "b": trace_b, "anon": trace_anon, "b_span": span_b}

    def _get(self, path: str, api_key: str):
        return self.client.get(
            path, headers={"Authorization": f"Bearer {api_key}"}
        )

    def _list_trace_ids(self, api_key: str) -> set[str]:
        resp = self._get("/audit/v1/traces/", api_key)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        return {t["trace_id"] for t in resp.get_json()["traces"]}

    # ---- unscoped keys keep global read ---------------------------

    def test_unscoped_read_key_sees_all_traces(self):
        seeded = self._seed_traces()
        admin = self._insert_key(["traces:read"])

        seen = self._list_trace_ids(admin)
        self.assertIn(seeded["a"], seen)
        self.assertIn(seeded["b"], seen)
        self.assertIn(seeded["anon"], seen)

    # ---- user-scoped reads ----------------------------------------

    def test_user_scoped_list_shows_only_bound_users_traces(self):
        seeded = self._seed_traces()
        scoped = self._insert_key(
            ["traces:read"], trace_user_id=USER_A
        )

        seen = self._list_trace_ids(scoped)
        self.assertIn(seeded["a"], seen)
        self.assertNotIn(seeded["b"], seen)
        self.assertNotIn(seeded["anon"], seen)

    def test_user_scoped_get_own_trace_ok_other_404(self):
        """By-id paths 404 on invisible traces: existence never leaks."""
        seeded = self._seed_traces()
        scoped = self._insert_key(
            ["traces:read"], trace_user_id=USER_A
        )

        own = self._get(f"/audit/v1/traces/{seeded['a']}/", scoped)
        self.assertEqual(own.status_code, 200)

        other = self._get(f"/audit/v1/traces/{seeded['b']}/", scoped)
        self.assertEqual(other.status_code, 404)

        anon = self._get(f"/audit/v1/traces/{seeded['anon']}/", scoped)
        self.assertEqual(anon.status_code, 404)

    def test_user_scoped_span_get_own_ok_other_404(self):
        seeded = self._seed_traces()
        scoped = self._insert_key(
            ["traces:read"], trace_user_id=USER_A
        )

        other = self._get(
            f"/audit/v1/traces/{seeded['b']}/spans/{seeded['b_span']}/",
            scoped,
        )
        self.assertEqual(other.status_code, 404)

    def test_user_scoped_spans_list_other_trace_404(self):
        seeded = self._seed_traces()
        scoped = self._insert_key(
            ["traces:read"], trace_user_id=USER_A
        )

        resp = self._get(
            f"/audit/v1/traces/{seeded['b']}/spans/", scoped
        )
        self.assertEqual(resp.status_code, 404)

    def test_user_scoped_search_scoped_to_bind(self):
        seeded = self._seed_traces()
        scoped = self._insert_key(
            ["traces:read"], trace_user_id=USER_A
        )

        # No identity filter: still scoped to the bind
        plain = self._get("/audit/v1/traces/search", scoped)
        self.assertEqual(
            {t["trace_id"] for t in plain.get_json()["traces"]},
            {seeded["a"]},
        )

        # Filter matching the bind: fine
        own = self._get(
            f"/audit/v1/traces/search?user_id={USER_A}", scoped
        )
        self.assertEqual(
            {t["trace_id"] for t in own.get_json()["traces"]},
            {seeded["a"]},
        )

        # Filter disagreeing with the bind: guaranteed-empty, not an
        # error and never the bind's own data
        conflict = self._get(
            f"/audit/v1/traces/search?user_id={USER_B}", scoped
        )
        self.assertEqual(conflict.status_code, 200)
        self.assertEqual(conflict.get_json()["traces"], [])

    # ---- client-scoped reads --------------------------------------

    def test_client_scoped_key_sees_only_bound_clients_traces(self):
        seeded = self._seed_traces()
        scoped = self._insert_key(
            ["traces:read"], trace_client_id=CLIENT_X
        )

        seen = self._list_trace_ids(scoped)
        self.assertIn(seeded["a"], seen)
        self.assertNotIn(seeded["b"], seen)

        # Both binds intersect: A's client + B's user is empty
        both = self._insert_key(
            ["traces:read"],
            trace_user_id=USER_B,
            trace_client_id=CLIENT_X,
        )
        self.assertNotIn(seeded["a"], self._list_trace_ids(both))
        self.assertNotIn(seeded["b"], self._list_trace_ids(both))

    # ---- journeys ---------------------------------------------------

    def test_journey_count_filtered_before_counting(self):
        """A scoped key's trace_count only counts traces it may see."""
        trace_a = uid.generate_trace_id()
        self._insert_span(
            trace_id=trace_a, span_id=uid.generate_span_id(),
            user_id=USER_A, journey_id=JOURNEY,
        )
        trace_b = uid.generate_trace_id()
        self._insert_span(
            trace_id=trace_b, span_id=uid.generate_span_id(),
            user_id=USER_B, journey_id=JOURNEY,
        )

        admin = self._insert_key(["traces:read"])
        scoped = self._insert_key(
            ["traces:read"], trace_user_id=USER_A
        )

        admin_view = self._get(f"/audit/v1/journeys/{JOURNEY}/", admin)
        self.assertEqual(admin_view.get_json()["trace_count"], 2)

        scoped_view = self._get(f"/audit/v1/journeys/{JOURNEY}/", scoped)
        self.assertEqual(scoped_view.get_json()["trace_count"], 1)
        self.assertEqual(
            {t["trace_id"] for t in scoped_view.get_json()["traces"]},
            {trace_a},
        )


class TestTraceBindMinting(IsolatedIntegrationTestCase):
    """Mint-side fail-closed rule (#944): keys granting trace reads
    without apikeys:write must carry a bind; admin-class keys may
    omit it. Binds are mint-time only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.audit_app = cls.manager.audit_app
        from campus.audit.resources.apikeys import APIKeysResource
        APIKeysResource.init_storage()

    def setUp(self):
        super().setUp()
        assert self.audit_app, "Audit app not initialized"
        self.client = self.audit_app.test_client()
        storage = campus.storage.tables.get_db("apikeys")
        with suppress(campus.storage.errors.NoChangesAppliedError):
            storage.delete_matching({})
        # One apikeys:write minter per test (inserted directly)
        self.minter = self._insert_key(["apikeys:read", "apikeys:write"])

    def _insert_key(self, scopes: list[str]) -> str:
        raw = secret.generate_audit_api_key()
        campus.storage.tables.get_db("apikeys").insert_one({
            "id": uid.generate_category_uid("apikey", length=16),
            "created_at": schema.DateTime.utcnow(),
            "key_hash": secret.hash_api_key(raw),
            "name": "minter",
            "owner_id": "test-user",
            "scopes": scopes,
        })
        return raw

    def _mint(self, body: dict):
        return self.client.post(
            "/audit/v1/apikeys/",
            json=body,
            headers={"Authorization": f"Bearer {self.minter}"},
        )

    def test_read_scoped_mint_without_bind_rejected(self):
        resp = self._mint({
            "name": "student-debug",
            "owner_id": "test-user",
            "scopes": ["traces:read"],
        })
        self.assertEqual(resp.status_code, 422)
        errors = resp.get_json()["error"]["errors"]
        self.assertEqual(errors[0]["code"], "MISSING_TRACE_BIND")

    def test_wildcard_and_producer_mints_are_exempt(self):
        """A wildcard grants apikeys:write (admin class); a
        traces:write key is a producer — neither needs a bind. This
        is what keeps the reviewed traces-producer role mintable.
        """
        wildcard = self._mint({
            "name": "wildcard",
            "owner_id": "test-user",
            "scopes": ["*"],
        })
        self.assertEqual(wildcard.status_code, 201)

        producer = self._mint({
            "name": "producer",
            "owner_id": "test-user",
            "scopes": ["traces:write", "traces:read"],
        })
        self.assertEqual(producer.status_code, 201)

        traces_wildcard = self._mint({
            "name": "traces-wildcard",
            "owner_id": "test-user",
            "scopes": ["traces:*"],
        })
        self.assertEqual(traces_wildcard.status_code, 201)

    def test_read_scoped_mint_with_user_bind_accepted(self):
        resp = self._mint({
            "name": "student-debug",
            "owner_id": "test-user",
            "scopes": ["traces:read"],
            "trace_user_id": USER_A,
        })
        self.assertEqual(resp.status_code, 201)
        record = resp.get_json()
        self.assertEqual(record["trace_user_id"], USER_A)
        self.assertIsNone(record["trace_client_id"])

    def test_view_role_mint_with_bind_accepted_without_bind_rejected(self):
        """role=traces-viewer resolves to traces:read — the same rule
        applies after role resolution."""
        with_bind = self._mint({
            "name": "student-viewer",
            "owner_id": "test-user",
            "role": "traces-viewer",
            "trace_user_id": USER_A,
        })
        self.assertEqual(with_bind.status_code, 201)

        without = self._mint({
            "name": "student-viewer",
            "owner_id": "test-user",
            "role": "traces-viewer",
        })
        self.assertEqual(without.status_code, 422)

    def test_admin_class_mint_without_bind_accepted(self):
        """apikeys:write holders (operator/admin class) mint unscoped."""
        resp = self._mint({
            "name": "admin-ui",
            "owner_id": "test-user",
            "scopes": ["apikeys:read", "apikeys:write", "traces:read"],
        })
        self.assertEqual(resp.status_code, 201)
        record = resp.get_json()
        self.assertIsNone(record["trace_user_id"])
        self.assertIsNone(record["trace_client_id"])

    def test_patch_rejects_bind_fields(self):
        """Binds are mint-time only: the API surface rejects the field
        (UNRECOGNIZED_FIELD), and no path mutates it."""
        created = self._mint({
            "name": "student-debug",
            "owner_id": "test-user",
            "scopes": ["traces:read"],
            "trace_user_id": USER_A,
        }).get_json()

        resp = self.client.patch(
            f"/audit/v1/apikeys/{created['id']}/",
            json={
                "name": "renamed",
                "trace_user_id": USER_B,
            },
            headers={"Authorization": f"Bearer {self.minter}"},
        )
        self.assertEqual(resp.status_code, 422)
        errors = resp.get_json()["error"]["errors"]
        self.assertEqual(errors[0]["code"], "UNRECOGNIZED_FIELD")

        # The bind survived the (rejected) attempt
        fetched = self.client.get(
            f"/audit/v1/apikeys/{created['id']}/",
            headers={"Authorization": f"Bearer {self.minter}"},
        ).get_json()
        self.assertEqual(fetched["trace_user_id"], USER_A)

        # A bind-free rename keeps the bind intact
        renamed = self.client.patch(
            f"/audit/v1/apikeys/{created['id']}/",
            json={"name": "renamed"},
            headers={"Authorization": f"Bearer {self.minter}"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.get_json()["trace_user_id"], USER_A)


if __name__ == "__main__":
    unittest.main()
