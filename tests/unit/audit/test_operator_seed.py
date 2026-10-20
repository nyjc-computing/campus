"""Unit tests pinning the operator key seed's scope shape.

The seeded operator key is the deployment's service credential. Per
the 2026-10-21 ruling on the student-access end state, it may bootstrap
API keys and ingest traces, and it may never read them: reading traces
is a human activity, done with the reader's own credentials (superadmin
OAuth or a traces:read key), not the deployment's credential.

File: tests/unit/audit/test_operator_seed.py
"""

import unittest


class TestOperatorSeedScopes(unittest.TestCase):
    """The seed's scope list is an invariant, not a convenience."""

    def test_operator_seed_scopes_are_exactly_bootstrap_plus_ingest(self):
        """apikeys:* for the bootstrap chicken-and-egg, traces:write for
        ingest — and nothing else. Any change to this set is a policy
        change and must update docs/audit-tracing.md too."""
        from campus.config import AUDIT_OPERATOR_API_KEY_SCOPES

        self.assertEqual(
            set(AUDIT_OPERATOR_API_KEY_SCOPES),
            {"apikeys:read", "apikeys:write", "traces:write"},
        )

    def test_operator_seed_holds_no_wildcard(self):
        """A wildcard on the seed would defeat the catalogue's
        no-wildcard rule at the one place keys are minted."""
        from campus.config import AUDIT_OPERATOR_API_KEY_SCOPES

        self.assertNotIn("*", AUDIT_OPERATOR_API_KEY_SCOPES)
