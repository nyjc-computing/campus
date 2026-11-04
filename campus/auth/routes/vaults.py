"""campus.auth.routes.vaults

Flask routes for vault management.

These routes handle creating, listing, retrieving, and deleting vault
keys. Vault labels hold deployment secrets (upstream OAuth client
credentials, scope caps, service configuration), so every route is
authorization-gated, not just authenticated (#854):

- the operator principal (AUTH_OPERATOR_CLIENT_IDS) may manage every
  label;
- any other authenticated client may only touch a label where it holds
  the matching vault_access bitflags: READ to list or read keys,
  CREATE or UPDATE to set, DELETE to delete (granted via
  /clients/{id}/access/ by the operator) — per-label only, never the
  label enumeration (#881, #1055);
- user bearers hold per-label access via grant rows and vaults:*
  scopes (#889), and may enumerate labels when they hold any vault
  grant plus the vaults:read scope (#1055).

Authentication is handled in a global routes.before_request hook.
"""

import flask

import campus.flask_campus as flask_campus
from campus.common.errors import api_errors
from campus.model.client import ClientAccess

from .. import authz, get_yapper
from ..resources import vault as vault_resource

# Create blueprint for vault management routes
bp = flask.Blueprint('vaults', __name__, url_prefix='/vaults')


@bp.get("/")
def list_labels() -> flask_campus.JsonResponse:
    """List vault labels

    GET /vaults/
    Authorization: the operator, the super-admin root, or a
    designated user holding any vault grant row with the vaults:read
    scope (#1055). Labels are groupings, not secrets — but the
    enumeration is an administrative view, so client principals stay
    per-label (#881).

    Returns: {
        "labels": ["apps", "storage", ...]
    }
    """
    authz.require_vault_enumeration()
    return {"labels": vault_resource.labels()}, 200


@bp.get("/<label>/")
@flask_campus.unpack_request
def keys(label: str) -> flask_campus.JsonResponse:
    """List a vault's keys

    GET /vaults/{label}/
    Authorization: READ vault access on {label}, or operator.

    Returns: [
        key_1,
        key_2,
        ...
    ]
    """
    authz.require_vault_permission(label, ClientAccess.READ)
    keys = vault_resource[label].keys()
    return {"keys": keys}, 200


@bp.delete("/<label>/<key>/")
@flask_campus.unpack_request
def delete(label: str, key: str) -> flask_campus.JsonResponse:
    """Delete a vault key

    DELETE /vaults/{label}/{key}/
    Authorization: DELETE vault access on {label}, or operator.

    Returns: {}
    """
    authz.require_vault_permission(label, ClientAccess.DELETE)
    del vault_resource[label][key]
    get_yapper().emit('campus.vaults.key.delete', {"label": label, "key": key})
    return {}, 200


@bp.get("/<label>/<key>/")
@flask_campus.unpack_request
def get(label: str, key: str) -> flask_campus.JsonResponse:
    """Get a vault value

    GET /vaults/{label}/{key}/
    Authorization: READ vault access on {label}, or operator.

    Returns: {
        "key": "value"
    }
    """
    authz.require_vault_permission(label, ClientAccess.READ)
    try:
        value = vault_resource[label][key]
    except KeyError:
        raise api_errors.NotFoundError("Key not found") from None
    return {"key": value}, 200


@bp.post("/<label>/<key>/")
@flask_campus.unpack_request
def set(label: str, key: str, value: str) -> flask_campus.JsonResponse:
    """Set a vault value

    POST /vaults/{label}/{key}/
    Authorization: CREATE or UPDATE vault access on {label}, or
    operator (set is create-or-update, so either bit authorizes it).

    Body: {
        "value": "new_value"
    }
    Returns: {
        "key": "value"
    }
    """
    authz.require_vault_permission(
        label, ClientAccess.CREATE | ClientAccess.UPDATE
    )
    vault_resource[label][key] = value
    get_yapper().emit('campus.vaults.key.update', {"label": label, "key": key})
    return {"key": value}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('vaults', __name__, url_prefix='/vaults')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "list_labels", list_labels, methods=["GET"])
    new_bp.add_url_rule("/<label>/", "keys", keys, methods=["GET"])
    new_bp.add_url_rule("/<label>/<key>/", "delete", delete, methods=["DELETE"])
    new_bp.add_url_rule("/<label>/<key>/", "get", get, methods=["GET"])
    new_bp.add_url_rule("/<label>/<key>/", "set", set, methods=["POST"])

    return new_bp
