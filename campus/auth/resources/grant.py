"""campus.auth.resources.grant

Access-grant resource for Campus API (#883, #884).

The generalized access-grant store: rows in the access_grants table
key authority by (grantee, resource, permission) — e.g. user u123
holds users:admin, client cl_ab holds READ|CREATE on vault label
mylabel. Vault grants store the CRUD bitflag mask
(campus.model.client.ClientAccess); management grants store a scope
level compared via the monotonic algebra in campus.auth.scopes — the
single comparison implementation (umbrella decision 1, #883).

The vault_access-era semantics are preserved for vault grants: grant
ORs bits into any existing row, revoke clears bits and deletes the row
at zero, update replaces the mask (zero deletes). Management levels
are monotonic: granting never lowers an existing level, and revoking
deletes the row only when the held level covers the revoked one.

Enforcement (require_resource_permission, #885) and the administration
routes (#886) build on this store; this module must stay ungated for
in-process callers, like the other resources.
"""

__all__ = ["GrantsResource", "grants", "grant_storage"]

import campus.model as model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
from campus.model.client import ClientAccess

from .. import scopes

grant_storage = campus.storage.get_table("access_grants")

VAULT = "vault"

_GRANTEE_TYPES = ("client", "user")
_RESOURCE_TYPES = (VAULT, "clients", "users", "credentials")
_LEVELS = ("read", "mod", "write", "admin")


def _scope(resource_type: str, level: str) -> str:
    """Compose the management scope name for a resource level."""
    return f"{resource_type}:{level}"


class GrantsResource:
    """Represents the access-grant resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize the access_grants table from the model."""
        grant_storage.init_from_model("access_grants", model.AccessGrant)

    def _validate(
            self,
            grantee_type: str,
            resource_type: str,
            bits: int | None,
            level: str | None,
    ) -> None:
        """Fail-closed validation of a grant's key and permission leg."""
        if grantee_type not in _GRANTEE_TYPES:
            raise api_errors.InvalidRequestError(
                "Invalid grantee type",
                grantee_type=grantee_type,
                accepted_values=list(_GRANTEE_TYPES),
            )
        if resource_type not in _RESOURCE_TYPES:
            raise api_errors.InvalidRequestError(
                "Invalid resource type",
                resource_type=resource_type,
                accepted_values=list(_RESOURCE_TYPES),
            )
        if resource_type == VAULT:
            if level is not None or bits is None:
                raise api_errors.InvalidRequestError(
                    "Vault grants carry a bitflag mask, not a scope level"
                )
            if not 0 <= bits <= ClientAccess.ALL:
                raise api_errors.InvalidRequestError(
                    "Invalid vault permission bitflag",
                    accepted_range=(
                        f"{ClientAccess.READ} - {ClientAccess.ALL}"
                    ),
                )
        else:
            if bits is not None or level not in _LEVELS:
                raise api_errors.InvalidRequestError(
                    "Management grants carry a scope level, not bitflags",
                    accepted_values=list(_LEVELS),
                )

    def _load(
            self,
            grantee_type: str,
            grantee_id: str,
            resource_type: str,
            resource_id: str,
    ) -> dict | None:
        """The single grant row for a (grantee, resource) key, if any."""
        records = grant_storage.get_matching({
            "grantee_type": grantee_type,
            "grantee_id": grantee_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
        })
        return records[0] if records else None

    def grant(
            self,
            grantee_type: str,
            grantee_id: str,
            resource_type: str,
            resource_id: str = "",
            *,
            bits: int | None = None,
            level: str | None = None,
    ) -> None:
        """Grant permission, OR-ing vault bits / raising levels only.

        Vault grants OR the given bits into the existing mask (the
        vault_access-era semantics); management grants never lower an
        existing level — monotonic, fail-closed.
        """
        self._validate(grantee_type, resource_type, bits, level)
        if resource_type == VAULT and bits == 0:
            return
        existing = self._load(
            grantee_type, grantee_id, resource_type, resource_id
        )
        if existing is None:
            grant_storage.insert_one({
                "id": uid.generate_category_uid("grant", length=8),
                "created_at": schema.DateTime.utcnow(),
                "grantee_type": grantee_type,
                "grantee_id": grantee_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "bits": bits,
                "level": level,
            })
            return
        if resource_type == VAULT:
            assert bits is not None
            grant_storage.update_by_id(existing["id"], {
                "bits": int(existing["bits"]) | bits,
            })
        else:
            assert level is not None
            if not scopes.grants(
                [_scope(resource_type, existing["level"])],
                _scope(resource_type, level),
            ):
                grant_storage.update_by_id(existing["id"], {
                    "level": level,
                })

    def revoke(
            self,
            grantee_type: str,
            grantee_id: str,
            resource_type: str,
            resource_id: str = "",
            *,
            bits: int | None = None,
            level: str | None = None,
    ) -> None:
        """Revoke permission; vault rows delete at zero bits.

        Revoking a management level deletes the row when the held
        level covers the revoked one — a revoke must guarantee the
        revoked level no longer checks, and a monotonic single-level
        row cannot shed an implied level, so the grant goes entirely
        (revoke users:admin from a users:admin holder deletes; revoke
        users:read from a users:write holder also deletes). Revoking
        above the held level is a no-op.
        """
        self._validate(grantee_type, resource_type, bits, level)
        if resource_type == VAULT and bits == 0:
            return
        existing = self._load(
            grantee_type, grantee_id, resource_type, resource_id
        )
        if existing is None:
            return
        if resource_type == VAULT:
            assert bits is not None
            remaining = int(existing["bits"]) & ~bits
            if remaining == 0:
                grant_storage.delete_by_id(existing["id"])
            else:
                grant_storage.update_by_id(existing["id"], {
                    "bits": remaining,
                })
        else:
            assert level is not None
            if scopes.grants(
                [_scope(resource_type, existing["level"])],
                _scope(resource_type, level),
            ):
                grant_storage.delete_by_id(existing["id"])

    def update(
            self,
            grantee_type: str,
            grantee_id: str,
            resource_type: str,
            resource_id: str = "",
            *,
            bits: int | None = None,
            level: str | None = None,
    ) -> None:
        """Replace the permission (zero bits deletes a vault grant)."""
        self._validate(grantee_type, resource_type, bits, level)
        existing = self._load(
            grantee_type, grantee_id, resource_type, resource_id
        )
        if existing is None:
            if resource_type == VAULT and bits == 0:
                return
            grant_storage.insert_one({
                "id": uid.generate_category_uid("grant", length=8),
                "created_at": schema.DateTime.utcnow(),
                "grantee_type": grantee_type,
                "grantee_id": grantee_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "bits": bits,
                "level": level,
            })
        elif resource_type == VAULT and bits == 0:
            grant_storage.delete_by_id(existing["id"])
        else:
            grant_storage.update_by_id(existing["id"], {
                "bits": bits, "level": level,
            })

    def get(
            self,
            grantee_type: str,
            grantee_id: str,
            resource_type: str,
            resource_id: str = "",
    ) -> dict | None:
        """The grant row for a (grantee, resource) key, if any."""
        return self._load(
            grantee_type, grantee_id, resource_type, resource_id
        )

    def check(
            self,
            grantee_type: str,
            grantee_id: str,
            resource_type: str,
            resource_id: str = "",
            *,
            bits: int | None = None,
            level: str | None = None,
    ) -> bool:
        """True if the grantee's row covers the requested permission.

        Vault grants match when ANY requested bit is held (the
        require_vault_permission semantics); management grants match
        via the monotonic scope algebra.
        """
        self._validate(grantee_type, resource_type, bits, level)
        existing = self._load(
            grantee_type, grantee_id, resource_type, resource_id
        )
        if existing is None:
            return False
        if resource_type == VAULT:
            assert bits is not None
            return bool(int(existing["bits"]) & bits)
        assert level is not None
        return scopes.grants(
            [_scope(resource_type, existing["level"])],
            _scope(resource_type, level),
        )

    def list(self, **filters: str) -> list[dict]:
        """List grant rows by any combination of key columns.

        This is the "who can administer what" matrix query (#872,
        #886): filter by grantee or resource, or list everything.
        """
        allowed = {
            key: value for key, value in filters.items()
            if key in (
                "grantee_type", "grantee_id",
                "resource_type", "resource_id",
            ) and value is not None
        }
        return grant_storage.get_matching(allowed)


grants = GrantsResource()
