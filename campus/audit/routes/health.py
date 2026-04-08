"""campus.audit.routes.health

Health check endpoint for the audit service.

Issue: #427
"""

import flask

from campus import flask_campus

# Create blueprint for health check routes
bp = flask.Blueprint('audit_health', __name__)


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialize health check routes.

    Args:
        app: The Flask app or blueprint to register routes on.
    """
    app.register_blueprint(bp)


@bp.get("/health")
def health_check() -> flask_campus.JsonResponse:
    """Health check endpoint (no authentication required).

    Returns:
        - 200 OK with {"status": "ok"} for JSON Accept header
        - 200 OK with "OK" plain text for text/plain Accept header
    """
    # TODO: Implement health check logic
    # - Check Accept header for content negotiation
    # - Return JSON for application/json
    # - Return plain text for text/plain
    # - No authentication required
    return {"status": "ok"}, 200
