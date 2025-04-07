"""palmtree.py

Authentication and authorization service for Campus.
"""

from flask import Blueprint, Flask

from .routes import emailotp


def create_app() -> Flask:
    """Factory function to create the Palmtree app."""
    bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')
    
    app = Flask(__name__)
    emailotp.init_app(bp)
    app.register_blueprint(bp)
    return app
