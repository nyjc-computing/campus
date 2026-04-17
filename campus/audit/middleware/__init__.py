"""campus.audit.middleware

Request tracing middleware for Campus audit API.

This module provides automatic span capture for HTTP requests flowing
through campus.auth and campus.api deployments.
"""

__all__ = ["init_app"]

import flask


def init_app(app: flask.Flask) -> None:
    """Initialize tracing middleware for the Flask app.

    Registers before_request and after_request hooks to capture
    request-response data as spans.

    Note: Should only be called for campus.auth and campus.api deployments,
    not for campus.audit (to avoid infinite recursion).

    Args:
        app: The Flask application to instrument.
    """
    from . import tracing

    @app.before_request
    def start_span():
        """Start a root span for each incoming request.

        Generates or reuses trace_id from X-Request-ID header.
        Stores timing and identifier data in flask.g for use in after_request.
        """
        tracing.start_span()

    @app.after_request
    def end_span(response):
        """Complete the span and send to audit service.

        Builds TraceSpan from request-response data and ingests asynchronously.
        Echoes trace_id in response headers for correlation.

        Args:
            response: The Flask response object.

        Returns:
            The response with X-Request-ID header added.
        """
        return tracing.end_span(response)
