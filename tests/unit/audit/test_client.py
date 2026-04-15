"""Unit tests for campus.audit.client module.

These tests verify that the audit HTTP client fulfills its interface contracts
and properly constructs API requests to the audit service.

Test Principles:
- Test interface contracts, not implementation
- Test resource chaining and path construction
- Do not test actual HTTP requests (those are contract tests)
"""

import unittest
from unittest.mock import Mock, patch

from campus.audit.client import AuditClient


class TestAuditClientInitialization(unittest.TestCase):
    """Test AuditClient initialization and configuration."""

    @patch("campus.audit.client._get_base_url")
    @patch("campus.common.http.DefaultClient")
    def test_client_initialization(self, mock_client_class, mock_get_base_url):
        """Test that AuditClient initializes with proper configuration."""
        mock_get_base_url.return_value = "https://audit.test"
        mock_http_client = Mock()
        mock_client_class.return_value = mock_http_client

        client = AuditClient()

        # Verify _get_base_url was called
        mock_get_base_url.assert_called_once()
        # Verify DefaultClient was instantiated with correct base_url
        mock_client_class.assert_called_once_with(base_url="https://audit.test")


class TestAuditClientResources(unittest.TestCase):
    """Test AuditClient resource access."""

    @patch("campus.audit.client._get_base_url")
    @patch("campus.common.http.DefaultClient")
    def test_traces_property_returns_traces_resource(self, mock_client_class, mock_get_base_url):
        """Test that client.traces returns Traces resource."""
        mock_get_base_url.return_value = "https://audit.test"
        mock_http_client = Mock()
        mock_http_client.base_url = "https://audit.test"
        mock_client_class.return_value = mock_http_client

        client = AuditClient()

        # Access traces property
        traces = client.traces

        # Verify it's a Traces resource
        from campus.audit.client.v1.traces import Traces
        self.assertIsInstance(traces, Traces)
        self.assertEqual(traces.root, client._root)
        self.assertEqual(traces.client, mock_http_client)


if __name__ == "__main__":
    unittest.main()
