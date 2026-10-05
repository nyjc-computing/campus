"""Unit tests for the device-code atomic claim (#356).

The token handler consumes an authorized device code by deleting it
BEFORE minting; claim() reports whether THIS call consumed the code,
so a concurrent poll that also observed "authorized" loses the race
with a clean InvalidGrantError instead of double-issuing a token.
"""

import unittest

from campus.common.utils import uid


class TestDeviceCodeClaim(unittest.TestCase):
    """DeviceCodeResource.claim() is single-use."""

    @classmethod
    def setUpClass(cls):
        # Lazy import: campus.auth pulls in storage modules at import
        # time. See AGENTS.md - Storage Initialization Order. The
        # resources package rebinds the name to the singleton instance.
        from campus.auth.resources import device_code as device_code_resource

        device_code_resource.init_storage()

    def test_claim_consumes_exactly_once(self):
        from campus.auth.resources import device_code as device_code_resource

        dc = device_code_resource.create(
            client_id="guest",
            scopes=["basic"],
        )

        self.assertTrue(device_code_resource.claim(dc.id))
        # The second claim loses: the code is already consumed
        self.assertFalse(device_code_resource.claim(dc.id))

    def test_claim_missing_code_returns_false(self):
        from campus.auth.resources import device_code as device_code_resource

        missing_id = uid.generate_category_uid("device_code")

        self.assertFalse(device_code_resource.claim(missing_id))
