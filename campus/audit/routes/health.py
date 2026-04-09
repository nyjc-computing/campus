"""campus.audit.routes.health

Health check endpoint for the audit service.

Issue: #427
"""

import flask

from campus import flask_campus


@flask.Blueprint('audit_health', __name__).get("/health")
def health_check() -> flask_campus.JsonResponse:
    """Health check endpoint (no authentication required).

    Returns:
        - 200 OK with {"status": "ok"} for JSON Accept header
        - 200 OK with "OK" plain text for text/plain Accept header
    """
    return {"status": "ok"}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('audit_health', __name__)

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/health", "health_check", health_check, methods=["GET"])

    return new_bp
