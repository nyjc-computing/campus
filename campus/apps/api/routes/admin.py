"""campus.apps.api.routes.admin

Admin routes for Campus API.
"""

from flask import Blueprint, Flask

from campus.common import devops

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/status", methods=["GET"])
def status():
    """Return admin status info."""
    return {"status": "ok", "message": "Admin endpoint is live."}


@bp.route("/init-db", methods=["POST"])
@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def init_db():
    """Initialise the tables needed by api."""
    from campus import models, vault
    models.circle.init_db()
    models.emailotp.init_db()
    models.user.init_db()
    vault.client.init_db()
    return {"status": "ok", "message": "Database initialised."}

# Purge DB endpoint


@bp.route("/purge-db", methods=["POST"])
@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def purge_db():
    """Purge the database."""
    from campus.storage import purge_all  # type: ignore[import-untyped]
    purge_all()
    return {"status": "ok", "message": f"{devops.ENV}: Database purged."}


def init_app(app: Blueprint | Flask) -> None:
    """Register the admin blueprint with the given Flask app or blueprint."""
    app.register_blueprint(bp)
