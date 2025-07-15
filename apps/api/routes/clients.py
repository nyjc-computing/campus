"""apps.api.routes.clients

API routes for the clients resource.
"""

from flask import Blueprint, Flask

import common.validation.flask as flask_validation
from apps.campusauth import authenticate_client
from apps.common.errors import api_errors
from apps.common.models import user
from services.vault import client as vault_client

bp = Blueprint('clients', __name__, url_prefix='/clients')
bp.before_request(authenticate_client)

# Database Models
users = user.User()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise client routes with the given Flask app/blueprint."""
    vault_client.init_db()
    app.register_blueprint(bp)


@bp.post('/')
def new_client() -> flask_validation.JsonResponse:
    """Create a new client id and secret."""
    payload = flask_validation.validate_request_and_extract_json(
        vault_client.ClientNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resource, client_secret = vault_client.create_client(**payload)
    # Return both the resource and the secret
    response_data = dict(resource)
    response_data["secret"] = client_secret
    flask_validation.validate_json_response(
        vault_client.ClientResourceWithSecret.__annotations__,
        response_data,
        on_error=api_errors.raise_api_error,
    )
    return response_data, 201


@bp.get('/')
def list_clients() -> flask_validation.JsonResponse:
    """List all clients."""
    clients_list = vault_client.list_clients()
    return {"clients": clients_list}, 200


@bp.delete('/<string:client_id>')
def delete_client(client_id: str) -> flask_validation.JsonResponse:
    """Delete a client id and secret."""
    try:
        vault_client.delete_client(client_id)
        return {}, 200
    except vault_client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e


@bp.get('/<string:client_id>')
def get_client_details(client_id: str) -> flask_validation.JsonResponse:
    """Get details of a client."""
    try:
        resource = vault_client.get_client(client_id)
        flask_validation.validate_json_response(
            vault_client.ClientResource.__annotations__,
            resource,
            on_error=api_errors.raise_api_error,
        )
        return dict(resource), 200
    except vault_client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e


@bp.patch('/<string:client_id>')
def edit_client(client_id: str) -> flask_validation.JsonResponse:
    """Edit name, description, or admins of client."""
    payload = flask_validation.validate_request_and_extract_json(
        vault_client.ClientNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    try:
        vault_client.update_client(client_id, **payload)
        return {}, 200
    except vault_client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e


@bp.post('/<string:client_id>/replace')
def revoke_client(client_id: str) -> flask_validation.JsonResponse:
    """Revoke a client id and secret, and reissue them."""
    try:
        new_secret = vault_client.replace_client_secret(client_id)
        return {"secret": new_secret}, 201
    except vault_client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e

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
