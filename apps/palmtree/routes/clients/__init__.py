from flask import Blueprint

from apps.palmtree.models import client

bp = Blueprint('clients', __name__, url_prefix='/clients')



def init_app(app) -> None:
    client.init_db()
    app.register_blueprint(bp)
    return app


@bp.post('/')
def apply_for_client():
    """Apply for a client id and secret."""
    return {"message": "not implemented"}, 501


@bp.patch('/')
def edit_client():
    """Edit name, description, or admins of client."""
    # TODO: admin required
    return {"message": "not implemented"}, 501


@bp.get('/applications/<string:application_id>')
def get_application_status(application_id: str):
    """Get the status of a client application."""
    return {"message": "not implemented"}, 501


@bp.post('/applications/<string:application_id>/approve')
def approve_application(application_id: str):
    """Approve a client application."""
    return {"message": "not implemented"}, 501


@bp.post('/applications/<string:application_id>/reject')
def reject_application(application_id: str):
    """Reject a client application."""
    return {"message": "not implemented"}, 501


@bp.get('/<string:client_id>')
def get_client_details(client_id: str):
    """Get details of a client."""
    return {"message": "not implemented"}, 501


@bp.post('/<string:client_id>/revoke')
def revoke_client(client_id: str):
    """Revoke a client id and secret, and reissue them."""
    return {"message": "not implemented"}, 501


@bp.get('/<string:client_id>/api_keys/')
def get_client_api_keys(client_id: str):
    """Get API keys requested by client admin."""
    return {"message": "not implemented"}, 501


@bp.post('/<string:client_id>/api_keys/create')
def create_client_api_key(client_id: str):
    """Create a new API key for the client."""
    return {"message": "not implemented"}, 501


@bp.delete('/<string:client_id>/api_keys/<string:name>')
def delete_client_api_key(client_id: str, name: str):
    """Delete an API key for the client."""
    return {"message": "not implemented"}, 501
