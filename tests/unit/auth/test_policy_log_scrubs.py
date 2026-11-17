"""Tests for the policy log-scrub fixes (#1126).

Railway stdout is a shared superadmin surface; policy §3 bans secrets
from logs. Covers: vault duplicate-row warnings no longer dump record
values, device/user codes are withheld from lookup-failure warnings,
and the logging tiers are opt-in, idempotent, and target real modules.
"""

import importlib
import logging
import unittest
from unittest import mock

from campus.logging_config import OAUTH_LOGGERS, configure_logging

# The resources package exposes singletons under these names; import the
# MODULES explicitly so the storage seams can be patched.
device_code_resource = importlib.import_module(
    "campus.auth.resources.device_code"
)
vault_resource = importlib.import_module("campus.auth.resources.vault")


class TestVaultWarningScrub(unittest.TestCase):
    """Duplicate-row warnings carry label/key/count, never values."""

    def test_warning_has_no_record_values(self):
        records = [
            {"key": "CLIENT_SECRET", "label": "apps", "value": "hunter2"},
            {"key": "CLIENT_SECRET", "label": "apps", "value": "hunter3"},
        ]
        with mock.patch.object(
                vault_resource, "vault_storage"
        ) as storage:
            storage.get_matching.return_value = records
            with self.assertLogs("campus.auth.resources.vault",
                                 level="WARNING") as captured:
                value = vault_resource.VaultResource("apps")["CLIENT_SECRET"]
        self.assertEqual(value, "hunter2")  # behavior unchanged
        joined = "\n".join(captured.output)
        self.assertNotIn("hunter2", joined)
        self.assertNotIn("hunter3", joined)
        self.assertIn("CLIENT_SECRET", joined)
        self.assertIn("2 records", joined)


class TestDeviceCodeWarningScrub(unittest.TestCase):
    """Lookup-failure warnings never echo the presented code."""

    def _assert_code_withheld(self, method_name, presented):
        resource = device_code_resource.DeviceCodeResource()
        with mock.patch.object(
                device_code_resource, "device_code_storage"
        ) as storage, self.assertLogs(
                "campus.auth.resources.device_code", level="WARNING"
        ) as captured:
            storage.get_matching.return_value = []
            with self.assertRaises(
                    device_code_resource.api_errors.NotFoundError
            ):
                getattr(resource, method_name)(presented)
        joined = "\n".join(captured.output)
        self.assertNotIn(presented, joined)

    def test_device_code_withheld(self):
        self._assert_code_withheld(
            "get_by_device_code",
            "WBD-464-HJKQ-NRTU-2026",
        )

    def test_user_code_withheld(self):
        self._assert_code_withheld(
            "get_by_user_code",
            "ABCD-EFGH",
        )


class TestLoggingConfiguration(unittest.TestCase):
    """OAuth debug tiers: opt-in, idempotent, real module names."""

    def test_oauth_debug_off_by_default(self):
        root = logging.getLogger()
        previous_level = root.level
        try:
            configure_logging()
            for name in OAUTH_LOGGERS:
                self.assertEqual(
                    logging.getLogger(name).level, logging.NOTSET,
                    f"{name} must stay at the inherited level by default",
                )
        finally:
            root.setLevel(previous_level)

    def test_oauth_debug_opt_in_sets_real_loggers(self):
        root = logging.getLogger()
        previous_level = root.level
        try:
            configure_logging(enable_oauth_debug=True)
            for name in OAUTH_LOGGERS:
                self.assertEqual(
                    logging.getLogger(name).level, logging.DEBUG,
                    f"{name} must honor the opt-in tier",
                )
        finally:
            for name in OAUTH_LOGGERS:
                logging.getLogger(name).setLevel(logging.NOTSET)
            root.setLevel(previous_level)

    def test_names_are_real_modules(self):
        """The tier targets modules that exist (the campus.apps.* names
        matched nothing after the split, silently disabling it)."""
        import importlib

        module_names = {
            name.rsplit(".", 1)[0] if name.endswith("routes") else name
            for name in OAUTH_LOGGERS
        }
        for module_name in module_names:
            importlib.import_module(module_name)

    def test_repeated_configuration_does_not_stack_handlers(self):
        root = logging.getLogger()
        previous_level = root.level
        try:
            configure_logging()
            configure_logging()
            self.assertEqual(len(root.handlers), 1)
        finally:
            root.setLevel(previous_level)


if __name__ == "__main__":
    unittest.main()
