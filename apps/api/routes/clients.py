"""apps.api.routes.clients

API routes for the clients resource.
"""

from flask import Blueprint, Flask

import common.validation.flask as flask_validation
from apps.campusauth import authenticate_client
from apps.common.errors import api_errors
from apps.common.models import user
from services.vault import client

bp = Blueprint('clients', __name__, url_prefix='/clients')
bp.before_request(authenticate_client)

# Database Models
users = user.User()


def init_app(app: Flask | Blueprint) -> None:
    """Initialise client routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/')
def new_client() -> flask_validation.JsonResponse:
    """Create a new client id and secret."""
    payload = flask_validation.validate_request_and_extract_json(
        client.ClientNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    resource, client_secret = client.create_client(**payload)
    # Return both the resource and the secret
    response_data = dict(resource)
    response_data["secret"] = client_secret
    flask_validation.validate_json_response(
        client.ClientResourceWithSecret.__annotations__,
        response_data,
        on_error=api_errors.raise_api_error,
    )
    return response_data, 201


@bp.get('/')
def list_clients() -> flask_validation.JsonResponse:
    """List all clients."""
    clients_list = client.list_clients()
    return {"clients": clients_list}, 200


@bp.delete('/<string:client_id>')
def delete_client(client_id: str) -> flask_validation.JsonResponse:
    """Delete a client id and secret."""
    try:
        client.delete_client(client_id)
        return {}, 200
    except client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e


@bp.get('/<string:client_id>')
def get_client_details(client_id: str) -> flask_validation.JsonResponse:
    """Get details of a client."""
    try:
        resource = client.get_client(client_id)
        flask_validation.validate_json_response(
            client.ClientResource.__annotations__,
            resource,
            on_error=api_errors.raise_api_error,
        )
        return dict(resource), 200
    except client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e


@bp.patch('/<string:client_id>')
def edit_client(client_id: str) -> flask_validation.JsonResponse:
    """Edit name, description, or admins of client."""
    payload = flask_validation.validate_request_and_extract_json(
        client.ClientNew.__annotations__,
        on_error=api_errors.raise_api_error,
    )
    try:
        client.update_client(client_id, **payload)
        return {}, 200
    except client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e


@bp.post('/<string:client_id>/replace')
def revoke_client(client_id: str) -> flask_validation.JsonResponse:
    """Revoke a client id and secret, and reissue them."""
    try:
        new_secret = client.replace_client_secret(client_id)
        return {"secret": new_secret}, 201
    except client.ClientAuthenticationError as e:
        raise api_errors.ConflictError(
            "Client not found",
            client_id=client_id
        ) from e
