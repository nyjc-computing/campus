from flask import Blueprint, request

from apps.api.models import client, user
from apps.common.errors import api_errors
from common.auth import authenticate_client
from common.schema import Message, Response

bp = Blueprint('clients', __name__, url_prefix='/clients')
bp.before_request(authenticate_client)

# Feature flags
GET = True
PATCH = False
POST = False
PUT = False
DELETE = False

# Database Models
clients = client.Client()
# apikeys = client.ClientAPIKey()
users = user.User()


def init_app(app) -> None:
    client.init_db()
    app.register_blueprint(bp)
    return app


@bp.post('/')
def new_client():
    """Create a new client id and secret."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate request, authenticate
    data = request.get_json()
    clients.new(**data)  # raises APIError
    return {"message": "Client created"}, 201

@bp.delete('/<string:client_id>')
def delete_client(client_id: str):
    """Delete a client id and secret."""
    if not DELETE:
        return {"message": "Not implemented"}, 501
    clients.delete(client_id)  # raises APIError
    return {"message": "Client deleted"}, 200

@bp.get('/<string:client_id>')
def get_client_details(client_id: str):
    """Get details of a client."""
    if not GET:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.get(client_id)  # raises APIError
    return resp.data, 200

@bp.patch('/<string:client_id>')
def edit_client():
    """Edit name, description, or admins of client."""
    if not PATCH:
        return {"message": "Not implemented"}, 501
    # TODO: validate request, authenticate
    data = request.get_json()
    clients.update(**data)  # raises APIError
    return {"message": "Client updated"}, 200

@bp.post('/<string:client_id>/replace')
def revoke_client(client_id: str):
    """Revoke a client id and secret, and reissue them."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.replace(client_id)  # raises APIError
    return resp.data, 201

@bp.get('/applications')
def get_client_applications():
    """Get all client applications."""
    if not GET:
        return {"message": "Not implemented"}, 501
    data = request.get_json()
    resp = clients.applications.list(**data)  # raises APIError
    return resp.data, 200

@bp.post('/applications')
def new_client_application():
    """Apply for a client id and secret."""
    if not POST:
        return {"message": "Not implemented"}, 501
    data = request.get_json()
    missing_fields = list(
        filter(
            lambda field: field not in data,
            ("owner", "name", "description")
        )
    )
    if missing_fields:
        raise api_errors.InvalidRequestError(
            message="Required fields missing",
            missing_fields=missing_fields
        )
    # Check owner exists
    # TODO: use token to authenticate user
    resp = users.get(data["owner"])  # raises APIError
    resp = clients.applications.new(**data)
    return {"message": "Client request submitted"}, 201

@bp.delete('/applications/<string:client_application_id>')
def delete_application(client_application_id: str):
    """Delete a client application."""
    if not DELETE:
        return {"message": "Not implemented"}, 501
    resp = clients.applications.delete(client_application_id)  # raises APIError
    return resp.data, 200

@bp.get('/applications/<string:client_application_id>')
def get_application_status(client_application_id: str):
    """Get the status of a client application."""
    if not GET:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.applications.get(client_application_id)  # raises APIError
    return resp.data, 200

@bp.put('/applications/<string:client_application_id>/approve')
def approve_application(client_application_id: str):
    """Approve a client application."""
    if not PUT:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    application = clients.applications.get(client_application_id).data
    # FUTURE: Migrate to flows
    resp = clients.new(
        name=application["name"],
        description=application["description"],
        admins=[application["owner"]],
    )
    resp = clients.applications.approve(client_application_id)  # raises APIError
    return resp.data, 201

@bp.put('/applications/<string:application_id>/reject')
def reject_application(client_application_id: str):
    """Reject a client application."""
    if not PUT:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.applications.reject(client_application_id)  # raises APIError
    return resp.data, 201


# @bp.get('/<string:client_id>/apikeys')
# def get_client_apikeys(client_id: str):
#     """Get API keys requested by client admin."""
#     if not GET:
#         return {"message": "Not implemented"}, 501
#     # TODO: validate, authenticate
#     resp = apikeys.get_apikeys(client_id)  # raises APIError
#     return resp.data, 200


# @bp.post('/<string:client_id>/apikeys')
# def new_client_api_key(client_id: str):
#     """Create a new API key for the client."""
#     if not POST:
#         return {"message": "not implemented"}, 501
#     # TODO: validate, authenticate
#     data = request.get_json()
#     resp = apikeys.new_api_key(client_id, **data)  # raises APIError
#     return resp.data, 201


# @bp.delete('/<string:client_id>/apikeys/<string:apikey_name>')
# def delete_client_api_key(client_id: str, apikey_name: str):
#     """Delete an API key for the client."""
#     if not DELETE:
#         return {"message": "not implemented"}, 501
#     # TODO: validate, authenticate
#     resp = apikeys.delete_api_key(client_id, apikey_name)  # raises APIError
#     return resp.data, 200

