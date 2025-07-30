"""apps.api.routes.admin

Admin routes for Campus API.
"""

from flask import Blueprint

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Example route


@bp.route("/status", methods=["GET"])
def status():
    """Return admin status info."""
    return {"status": "ok", "message": "Admin endpoint is live."}


def init_app(app):
    """Register the admin blueprint with the given Flask app or blueprint."""
    app.register_blueprint(bp)
