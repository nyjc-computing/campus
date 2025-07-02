"""apps.api.routes.clients

API routes for the clients resource.
"""

from flask import Blueprint, Flask

from apps.campusauth.model import authenticate_client
from apps.common.errors import api_errors
from apps.common.models import client, user
import common.validation.flask as flask_validation

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
def new_client() -> flask_validation.JsonResponse:
    """Create a new client id and secret."""
    payload = flask_validation.validate_request_and_extract_json(
        client.ClientNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resp = clients.new(**payload)  # raises APIError
    flask_validation.validate_json_response(
        resp.data,
        client.ClientResource.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    return resp.data, 201


@bp.delete('/<string:client_id>')
def delete_client(client_id: str) -> flask_validation.JsonResponse:
    """Delete a client id and secret."""
    resp = clients.delete(client_id)
    flask_validation.validate_json_response(
        resp.data,
        {"message": str},
        on_error=api_errors.raise_api_error,
    )
    return {"message": "Client deleted"}, 200


@bp.get('/<string:client_id>')
def get_client_details(client_id: str) -> flask_validation.JsonResponse:
    """Get details of a client."""
    resp = clients.get(client_id)
    flask_validation.validate_json_response(
        resp.data,
        client.ClientResource.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    return resp.data, 200


@bp.patch('/<string:client_id>')
def edit_client(client_id: str) -> flask_validation.JsonResponse:
    """Edit name, description, or admins of client."""
    payload = flask_validation.validate_request_and_extract_json(
        client.ClientUpdate.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resp = clients.update(client_id, **payload)
    flask_validation.validate_json_response(
        resp.data,
        client.ClientResource.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    return resp.data, 200


@bp.post('/<string:client_id>/replace')
def revoke_client(client_id: str) -> flask_validation.JsonResponse:
    """Revoke a client id and secret, and reissue them."""
    if not POST:
        return {"message": "Not implemented"}, 501
    resp = clients.replace(client_id)
    flask_validation.validate_json_response(
        resp.data,
        client.ClientResource.__annotations__,
        on_error=api_errors.raise_api_error,
    )
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
