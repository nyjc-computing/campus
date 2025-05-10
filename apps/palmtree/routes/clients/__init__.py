from flask import Blueprint, request

from apps.palmtree.models import client, user
from apps.palmtree.errors import api_errors
from common.schema import Message, Response

bp = Blueprint('clients', __name__, url_prefix='/clients')

# Feature flags
GET = True
PATCH = False
POST = False
DELETE = False

# Database Models
client_requests = client.ClientIdRequest()
clients = client.Client()
api_keys = client.ClientAPIKey()
users = user.User()


def init_app(app) -> None:
    client.init_db()
    app.register_blueprint(bp)
    return app


@bp.post('/applications')
def apply_for_client():
    """Apply for a client id and secret."""
    if not POST:
        return {"message": "Not implemented"}, 501
    data = request.get_json()
    missing_fields = list(
        filter(
            lambda field: field not in data,
            ("requester", "name", "description")
        )
    )
    if missing_fields:
        raise api_errors.InvalidRequestError(
            message="Required fields missing",
            missing_fields=missing_fields
        )
    # Check requester exists
    # TODO: use token to authenticate user
    resp = users.get(data["requester"])  # raises APIError
    resp = client_requests.submit_client_request(**data)
    return {"message": "Client request submitted"}, 201


@bp.patch('/')
def edit_client():
    """Edit name, description, or admins of client."""
    if not PATCH:
        return {"message": "Not implemented"}, 501
    # TODO: validate request, authenticate
    data = request.get_json()
    clients.update_client(**data)  # raises APIError
    return {"message": "Client updated"}, 200


@bp.get('/applications/<string:client_request_id>')
def get_application_status(client_request_id: str):
    """Get the status of a client application."""
    if not GET:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = client_requests.get_client_request(client_request_id)  # raises APIError
    return resp.data, 200

@bp.post('/applications/<string:client_request_id>/approve')
def approve_application(client_request_id: str):
    """Approve a client application."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = client_requests.approve_client_request(client_request_id)  # raises APIError
    return resp.data, 201


@bp.post('/applications/<string:application_id>/reject')
def reject_application(client_request_id: str):
    """Reject a client application."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = client_requests.reject_client_request(client_request_id)  # raises APIError
    return resp.data, 201


@bp.get('/<string:client_id>')
def get_client_details(client_id: str):
    """Get details of a client."""
    if not GET:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.get_client(client_id)  # raises APIError
    return resp.data, 200


@bp.post('/<string:client_id>/revoke')
def revoke_client(client_id: str):
    """Revoke a client id and secret, and reissue them."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.revoke_client(client_id)  # raises APIError
    return resp.data, 201


# @bp.get('/<string:client_id>/api_keys/')
# def get_client_api_keys(client_id: str):
#     """Get API keys requested by client admin."""
#     if not GET:
#         return {"message": "Not implemented"}, 501
#     # TODO: validate, authenticate
#     resp = api_keys.get_api_keys(client_id)  # raises APIError
#     return resp.data, 200


# @bp.post('/<string:client_id>/api_keys/create')
# def create_client_api_key(client_id: str):
#     """Create a new API key for the client."""
#     if not POST:
#         return {"message": "not implemented"}, 501
#     # TODO: validate, authenticate
#     data = request.get_json()
#     resp = api_keys.create_api_key(client_id, **data)  # raises APIError
#     return resp.data, 201


# @bp.delete('/<string:client_id>/api_keys/<string:name>')
# def delete_client_api_key(client_id: str, name: str):
#     """Delete an API key for the client."""
#     if not DELETE:
#         return {"message": "not implemented"}, 501
#     # TODO: validate, authenticate
#     resp = api_keys.delete_api_key(client_id, name)  # raises APIError
#     return resp.data, 200

