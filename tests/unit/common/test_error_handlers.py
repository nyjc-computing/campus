"""campus.tests.unit.common.test_error_handlers

Unit tests for campus.common.errors.handlers frame selection.

get_caller() is used by the Flask error handlers to name the module an
unhandled exception originated from. Logs must point at the campus code
that made the failing call, not the adapter or client library that raised
(#620).
"""

import traceback
import unittest

from campus.common.errors import handlers

# Synthetic campus frames must live under the real package dir so that
# _select_campus_frame's is_relative_to check matches, whatever the checkout
# path is. Non-campus frames use paths that resolve outside it.
PKG = str(handlers._CAMPUS_PKG_DIR)


def _frame(filename: str) -> traceback.FrameSummary:
    """Build a synthetic traceback frame for frame-selection tests."""
    return traceback.FrameSummary(filename, lineno=1, name="test")


def _raise_in_schema_helper() -> None:
    """Raise through a real campus module to exercise the sys.exc_info path."""
    from campus.common import schema

    schema.DateTime(None)


class TestGetCaller(unittest.TestCase):
    """Tests for get_caller() traceback frame selection."""

    def test_selects_outermost_campus_frame_over_raiser(self):
        """Should name the campus caller, not a site-packages raise site."""
        frames = [
            _frame("/srv/app/tests/flask_test/response.py"),
            _frame(PKG + "/api/__init__.py"),
            _frame("/srv/venv/site-packages/campus_python/auth/v1/root.py"),
        ]
        self.assertEqual(
            handlers._select_campus_frame(frames),
            PKG + "/api/__init__.py",
        )

    def test_selects_campus_over_deeper_campus_adapter(self):
        """Should prefer the outermost campus frame over an inner campus frame."""
        frames = [
            _frame("/srv/venv/site-packages/flask/app.py"),
            _frame(PKG + "/auth/routes/root.py"),
            _frame(PKG + "/auth/resources/vault.py"),
        ]
        self.assertEqual(
            handlers._select_campus_frame(frames),
            PKG + "/auth/routes/root.py",
        )

    def test_skips_error_handler_frames(self):
        """Should not name the error-handler machinery as the origin."""
        frames = [
            _frame(str(handlers._HANDLER_DIR) + "/handlers.py"),
            _frame(PKG + "/auth/resources/user.py"),
        ]
        self.assertEqual(
            handlers._select_campus_frame(frames),
            PKG + "/auth/resources/user.py",
        )

    def test_falls_back_to_raise_site_without_campus_frames(self):
        """Should report no campus frame when the chain has none.

        get_caller() falls back to the innermost frame in that case.
        """
        frames = [
            _frame("/srv/venv/site-packages/flask/app.py"),
            _frame("/srv/venv/site-packages/requests/sessions.py"),
        ]
        self.assertIsNone(handlers._select_campus_frame(frames))

    def test_get_caller_names_campus_module_not_test_file(self):
        """Should resolve the campus origin from a live exception context."""
        try:
            _raise_in_schema_helper()
        except ValueError:
            module = handlers.get_caller()
        else:
            self.fail("schema.DateTime(None) should raise ValueError")
        self.assertNotIn("test_error_handlers", module)
        self.assertIn("campus", module)


if __name__ == "__main__":
    unittest.main()
