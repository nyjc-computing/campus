"""apps.api.routes.clients

API routes for the clients resource.
"""

from typing import Unpack

from flask import Blueprint, Flask

from apps.campusauth.model import authenticate_client
from apps.common.errors import api_errors
from apps.common.models import client, user
from common.validation.flask import FlaskResponse, unpack_request, validate

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


def init_app(app: Flask | Blueprint) -> None:
    """Initialise client routes with the given Flask app/blueprint."""
    client.init_db()
    app.register_blueprint(bp)


@bp.post('/')
@unpack_request
@validate(
    request=client.ClientNew.__annotations__,
    response=client.ClientResource.__annotations__,
    on_error=api_errors.raise_api_error
)
# *_ appease linter
def new_client(*_: str, **data: Unpack[client.ClientNew]) -> FlaskResponse:
    """Create a new client id and secret."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: authenticate
    resp = clients.new(**data)  # raises APIError
    return resp.data, 201


@bp.delete('/<string:client_id>')
@validate(
    response={"message": str},
    on_error=api_errors.raise_api_error
)
def delete_client(client_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Delete a client id and secret."""
    if not DELETE:
        return {"message": "Not implemented"}, 501
    resp = clients.delete(client_id)  # raises APIError
    return {"message": "Client deleted"}, 200


@bp.get('/<string:client_id>')
@validate(
    response=client.ClientResource.__annotations__,
    on_error=api_errors.raise_api_error
)
def get_client_details(client_id: str, *_, **__) -> FlaskResponse:  # *_ appease linter
    """Get details of a client."""
    if not GET:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.get(client_id)  # raises APIError
    return resp.data, 200


@bp.patch('/<string:client_id>')
@unpack_request
@validate(
    request=client.ClientUpdate.__annotations__,
    response=client.ClientResource.__annotations__,
    on_error=api_errors.raise_api_error
)
# *_ appease linter
def edit_client(client_id: str, *_, **data: Unpack[client.ClientUpdate]) -> FlaskResponse:
    """Edit name, description, or admins of client."""
    if not PATCH:
        return {"message": "Not implemented"}, 501
    # TODO: authenticate
    resp = clients.update(client_id, **data)  # raises APIError
    return resp.data, 200


@bp.post('/<string:client_id>/replace')
@validate(
    response=client.ClientReplaceResponse.__annotations__,
    on_error=api_errors.raise_api_error
)
def revoke_client(client_id: str, *_, **__) -> FlaskResponse:
    """Revoke a client id and secret, and reissue them."""
    if not POST:
        return {"message": "Not implemented"}, 501
    # TODO: validate, authenticate
    resp = clients.replace(client_id)  # raises APIError
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
