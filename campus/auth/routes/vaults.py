"""campus.auth.routes.vaults

Flask routes for vault management.

These routes handle creating, listing, retrieving, and deleting vaults.
Admin operations require ALL permissions, read operations require READ permissions.

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus.common import flask_campus
import campus.yapper

from ..resources import vault as vault_resource

# Create blueprint for vault management routes
bp = flask.Blueprint('vaults', __name__, url_prefix='/vaults')

# Lazy-loaded yapper instance to avoid circular dependencies
_yapper_instance = None


def get_yapper():
    """Get yapper instance, creating it lazily to avoid circular
    dependencies."""
    global _yapper_instance
    if _yapper_instance is None:
        _yapper_instance = campus.yapper.create()
    return _yapper_instance


@bp.get("/<label>/")
@flask_campus.unpack_request
def keys(label: str) -> flask_campus.JsonResponse:
    """Get the keys for a specific vault.

    GET /vaults/{label}/

    Returns: [
        key_1,
        key_2,
        ...
    ]
    """
    keys = vault_resource[label].keys()
    return {"keys": keys}, 200


@bp.delete("/<label>/<key>")
@flask_campus.unpack_request
def delete(label: str, key: str) -> flask_campus.JsonResponse:
    """Delete a key from a vault.

    DELETE /vaults/{label}/{key}
    Returns: {}
    """
    del vault_resource[label][key]
    get_yapper().emit('campus.vaults.key.delete', {"label": label, "key": key})
    return {}, 200


@bp.get("/<label>/<key>")
@flask_campus.unpack_request
def get(label: str, key: str) -> flask_campus.JsonResponse:
    """Get a specific key from a vault.

    GET /vaults/{label}/{key}

    Returns: {
        "key": "value"
    }
    """
    try:
        value = vault_resource[label][key]
    except KeyError:
        return {"error": "Key not found"}, 404
    return {"key": value}, 200


@bp.post("/<label>/<key>")
@flask_campus.unpack_request
def set(label: str, key: str, value: str) -> flask_campus.JsonResponse:
    """Set a specific key in a vault.

    POST /vaults/{label}/{key}
    Body: {
        "value": "new_value"
    }
    Returns: {
        "key": "value"
    }
    """
    vault_resource[label][key] = value
    get_yapper().emit('campus.vaults.key.update', {"label": label, "key": key})
    return {"key": value}, 200
