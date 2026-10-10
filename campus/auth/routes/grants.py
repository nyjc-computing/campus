"""campus.auth.routes.grants

Flask routes for the access-grant store (#883, #886).

The administration surface for generalized grant rows: list (the
"who can administer what" matrix query, #872), grant, revoke, delete,
and check — for both client and user grantees across the resource
vocabularies. The vault-only /clients/{id}/access/ routes remain as a
compat alias over the same store, on their own deprecation schedule.

Administration matrix (umbrella decision 5, #883):

- the operator principal may administer every vocabulary;
- a user principal holding <vocabulary>:admin — grant row AND token
  scope, via require_resource_permission (#885) — may administer that
  vocabulary only. Administration requires the admin level, the top
  of each vocabulary, so no principal can grant above its own level
  (structurally enforced);
- vault grants are operator-only to administer: the vault vocabulary
  is reserved for user principals until #889, so the gate denies
  every non-operator on it;
- clients may not administer grants at all (clients are never
  designated admins, #854/#865).

Grant-shape guards (umbrella decisions 4-5), applied to every
mutation regardless of the caller:

- no self-grants: a user principal may not create or raise a grant
  naming itself (the operator client granting itself vault bits is
  the pre-#886 model and stays allowed — bootstrap semantics);
- no operator-equivalent rows: a vocabulary-level clients:admin grant
  would recreate the operator outside AUTH_OPERATOR_CLIENT_IDS, so it
  is rejected outright;
- reserved vocabularies stay closed: credentials grants and
  user-principal vault grants are rejected until #889 pins their
  matrices.

Bootstrap: the operator env-var leg (AUTH_OPERATOR_CLIENT_IDS) mints
the first grants (break-glass); every later grant flows through here
with yapper events and the audit middleware stamping the acting
principal (#802).

Authentication is handled in a global routes.before_request hook.
"""

import flask

from campus import flask_campus
from campus.common.errors import api_errors

from .. import authz, get_yapper
from ..resources.grant import grants

# Create blueprint for grant administration routes
bp = flask.Blueprint('grants', __name__, url_prefix='/grants')


def _require_grant_admin(resource_type: str) -> None:
    """Require authority to administer `resource_type`'s grants.

    Delegates to the generalized gate (#885), which settles user
    principals before the operator bypass — a user minted through
    the operator client must not inherit its role (#854). A user
    needs <resource_type>:admin via a grant row AND a token scope;
    the vault vocabulary is therefore operator-only (reserved for
    users until #889); clients are denied everywhere (#854).
    """
    authz.require_resource_permission(resource_type, "admin")


def _forbid_self_grant(grantee_type: str, grantee_id: str) -> None:
    """Reject a user principal administering its own grant (#883)."""
    if authz.is_user_principal():
        user = flask.g.current_user
        if (
                grantee_type == "user"
                and str(user.get("id")) == str(grantee_id)
        ):
            raise api_errors.ForbiddenError(
                "User principals may not administer their own access "
                "grants (#883): self-grants would bypass the "
                "designation review"
            )


def _forbid_forbidden_shapes(
        grantee_type: str,
        resource_type: str,
        level: str | None,
) -> None:
    """Reject grant shapes the epic keeps closed (#883 decisions 4, 5).

    - vocabulary-level clients:admin rows are operator-equivalent;
    - the credentials vocabulary is reserved until #889;
    - user-principal vault grants are reserved until #889.
    """
    if resource_type == "clients" and level == "admin":
        raise api_errors.ForbiddenError(
            "A vocabulary-level 'clients:admin' grant is "
            "operator-equivalent (#883): operator authority comes "
            f"only from {authz.OPERATOR_CLIENT_IDS_ENVVAR}"
        )
    if resource_type == "credentials":
        raise api_errors.ForbiddenError(
            "The credentials vocabulary is reserved (#883): its "
            "routes are operator-only until campus#889 pins a "
            "grants matrix for it"
        )
    if resource_type == "vault" and grantee_type == "user":
        raise api_errors.ForbiddenError(
            "Vault grants for user principals are reserved (#883) "
            "until campus#889 pins their matrix"
        )


def _grant_event_name(operation: str) -> str:
    return f"campus.grants.{operation}"


@bp.get("/")
@flask_campus.unpack_request
def list_grants(
        grantee_type: str | None = None,
        grantee_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
) -> flask_campus.JsonResponse:
    """List access-grant rows.

    GET /grants
    Authorization: operator for the full matrix; otherwise a
    same-vocabulary admin scoped to that vocabulary
    (resource_type=<their vocabulary>).

    Query: grantee_type, grantee_id, resource_type, resource_id
    (all optional; unfiltered requires the operator).

    Returns: {"grants": [AccessGrant]}
    """
    if authz.is_user_principal():
        # Users see exactly one vocabulary — the one they administer.
        if resource_type is None:
            # require_operator raises for user principals here
            authz.require_operator("list access grants")
        assert resource_type is not None
        _require_grant_admin(resource_type)
    elif not authz.is_operator():
        authz.require_operator("list access grants")
    rows = grants.list(
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return {"grants": rows}, 200


@bp.get("/check")
@flask_campus.unpack_request
def check_grant(
        grantee_type: str,
        grantee_id: str,
        resource_type: str,
        resource_id: str = "",
        bits: int | None = None,
        level: str | None = None,
) -> flask_campus.JsonResponse:
    """Check whether a grantee's row covers a permission.

    GET /grants/check
    Authorization: operator, or a same-vocabulary admin.

    Query: grantee_type, grantee_id, resource_type, resource_id,
    bits | level.

    Returns: {"granted": bool}
    """
    _require_grant_admin(resource_type)
    granted = grants.check(
        grantee_type, grantee_id, resource_type, resource_id,
        bits=bits, level=level,
    )
    return {"granted": granted}, 200


@bp.post("/")
@flask_campus.unpack_request
def grant(
        grantee_type: str,
        grantee_id: str,
        resource_type: str,
        resource_id: str = "",
        bits: int | None = None,
        level: str | None = None,
) -> flask_campus.JsonResponse:
    """Grant access (create a row, or raise an existing one).

    POST /grants
    Authorization: operator, or same-vocabulary admin. Vault bits
    OR into the existing mask; management levels never downgrade.

    Body: {
        "grantee_type": "user",
        "grantee_id": "u1",
        "resource_type": "users",
        "resource_id": "",
        "level": "admin"
    }

    Returns: {"grant": AccessGrant}
    """
    _require_grant_admin(resource_type)
    _forbid_self_grant(grantee_type, grantee_id)
    _forbid_forbidden_shapes(grantee_type, resource_type, level)
    grants.grant(
        grantee_type, grantee_id, resource_type, resource_id,
        bits=bits, level=level,
    )
    get_yapper().emit(_grant_event_name("grant"), {
        "grantee_type": grantee_type,
        "grantee_id": grantee_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
    })
    row = grants.get(grantee_type, grantee_id, resource_type, resource_id)
    return {"grant": row}, 201


@bp.post("/revoke")
@flask_campus.unpack_request
def revoke(
        grantee_type: str,
        grantee_id: str,
        resource_type: str,
        resource_id: str = "",
        bits: int | None = None,
        level: str | None = None,
) -> flask_campus.JsonResponse:
    """Revoke access (clear vault bits, delete covered levels).

    POST /grants/revoke
    Authorization: operator, or same-vocabulary admin. Vault rows
    delete at zero bits; a revoked level's row is deleted when the
    held level covers it (#884 semantics).

    Body: same shape as POST /grants

    Returns: {"grant": AccessGrant | null}
    """
    _require_grant_admin(resource_type)
    _forbid_self_grant(grantee_type, grantee_id)
    grants.revoke(
        grantee_type, grantee_id, resource_type, resource_id,
        bits=bits, level=level,
    )
    get_yapper().emit(_grant_event_name("revoke"), {
        "grantee_type": grantee_type,
        "grantee_id": grantee_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
    })
    row = grants.get(grantee_type, grantee_id, resource_type, resource_id)
    return {"grant": row}, 200


@bp.delete("/<grant_id>")
@flask_campus.unpack_request
def delete_grant(grant_id: str) -> flask_campus.JsonResponse:
    """Delete a grant row outright.

    DELETE /grants/{grant_id}
    Authorization: operator, or a same-vocabulary admin for the
    row's vocabulary.

    Returns: {}
    """
    rows = grants.list()
    row = next((r for r in rows if str(r.get("id")) == grant_id), None)
    if row is None:
        raise api_errors.NotFoundError("Grant not found")
    resource_type = row["resource_type"]
    _require_grant_admin(resource_type)
    _forbid_self_grant(row["grantee_type"], row["grantee_id"])
    from ..resources.grant import grant_storage
    grant_storage.delete_by_id(row["id"])
    get_yapper().emit(_grant_event_name("delete"), {"id": grant_id})
    return {}, 200


def create_blueprint() -> flask.Blueprint:
    """Create a fresh blueprint with routes for test isolation.

    Creates a new blueprint instance and manually registers all route
    functions to support creating multiple independent Flask apps.
    """
    new_bp = flask.Blueprint('grants', __name__, url_prefix='/grants')

    # Manually register routes (mimicking the decorator behavior)
    new_bp.add_url_rule("/", "list_grants", list_grants, methods=["GET"])
    new_bp.add_url_rule("/check", "check_grant", check_grant, methods=["GET"])
    new_bp.add_url_rule("/", "grant", grant, methods=["POST"])
    new_bp.add_url_rule("/revoke", "revoke", revoke, methods=["POST"])
    new_bp.add_url_rule("/<grant_id>", "delete_grant", delete_grant, methods=["DELETE"])

    return new_bp
