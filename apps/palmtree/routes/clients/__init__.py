from flask import Blueprint, request

from apps.palmtree.models import client
from common.schema import Message

bp = Blueprint('clients', __name__, url_prefix='/clients')

# Feature flags
GET = True
PATCH = False
POST = False

# Database Models
client_requests = client.ClientIdRequest()
clients = client.Client()
api_keys = client.ClientAPIKey()


def init_app(app) -> None:
    client.init_db()
    app.register_blueprint(bp)
    return app


@bp.post('/')
def apply_for_client():
    """Apply for a client id and secret."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate request
    data = request.get_json()
    resp = client_requests.submit_client_request(**data)
    match resp:
        case ("error", msg, _):
            return {"error": msg}, 500
        case ("ok", Message.CREATED, _):
            return {"message": "Client request submitted"}, 201
    return {"message": "unexpected error occurred"}, 500


@bp.patch('/')
def edit_client():
    """Edit name, description, or admins of client."""
    if not PATCH:
        return {"message": "Not implemented"}, 501
    # TODO: validate request, authenticate
    data = request.get_json()
    resp = clients.update_client(**data)
    match resp:
        case ("error", msg, _):
            return {"error": msg}, 500
        case ("ok", Message.UPDATED, _):
            return {"message": "Client updated"}, 200
    return {"message": "unexpected error occurred"}, 500


@bp.get('/applications/<string:client_request_id>')
def get_application_status(client_request_id: str):
    """Get the status of a client application."""
    if not GET:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = client_requests.get_client_request(client_request_id)
    match resp:
        case ("error", msg, _):
            return {"error": msg}, 500
        case ("ok", Message.FOUND, result):
            return result, 200
    return {"message": "unexpected error occurred"}, 500

@bp.post('/applications/<string:client_request_id>/approve')
def approve_application(client_request_id: str):
    """Approve a client application."""
    # TODO: validate, authenticate
    return {"message": "not implemented"}, 501


@bp.post('/applications/<string:application_id>/reject')
def reject_application(client_request_id: str):
    """Reject a client application."""
    return {"message": "not implemented"}, 501


@bp.get('/<string:client_id>')
def get_client_details(client_id: str):
    """Get details of a client."""
    # TODO: validate, authenticate
    resp = clients.get_client(client_id)
    match resp:
        case ("error", msg, _):
            return {"error": msg}, 500
        case ("ok", Message.FOUND, result):
            return result, 200
    return {"message": "unexpected error occurred"}, 500


@bp.post('/<string:client_id>/revoke')
def revoke_client(client_id: str):
    """Revoke a client id and secret, and reissue them."""
    return {"message": "not implemented"}, 501


@bp.get('/<string:client_id>/api_keys/')
def get_client_api_keys(client_id: str):
    """Get API keys requested by client admin."""
    # TODO: validate, authenticate
    resp = api_keys.get_api_keys(client_id)
    match resp:
        case ("error", msg, _):
            return {"error": msg}, 500
        case ("ok", Message.FOUND, result):
            return result, 200
    return {"message": "unexpected error occurred"}, 500


@bp.post('/<string:client_id>/api_keys/create')
def create_client_api_key(client_id: str):
    """Create a new API key for the client."""
    return {"message": "not implemented"}, 501


@bp.delete('/<string:client_id>/api_keys/<string:name>')
def delete_client_api_key(client_id: str, name: str):
    """Delete an API key for the client."""
    return {"message": "not implemented"}, 501
