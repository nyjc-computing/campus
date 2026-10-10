"""campus.model.grant

Access-grant model for Campus API.
"""

from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import uid

from .base import Model


@dataclass(eq=False, kw_only=True)
class AccessGrant(Model):
    """Represents a designated access grant over a management resource.

    Generalizes the vault-only client-access model (#883): a grant row
    keys authority by grantee (client or user), resource vocabulary,
    and — for vaults — the specific label. Vault grants carry the CRUD
    bitflag mask in `bits` (campus.model.client.ClientAccess);
    management-resource grants carry the scope level in `level`
    (read < mod < write < admin, compared via campus.auth.scopes).
    `resource_id` is the vault label for vault grants and the empty
    string for vocabulary-level grants (NULLs would be distinct under
    a unique constraint; the store dedupes in the upsert instead).
    """

    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("grant", length=8)
    ))
    # created_at is inherited from Model
    grantee_type: schema.String  # "client" | "user"
    grantee_id: schema.CampusID
    resource_type: schema.String  # "vault" | "clients" | "users" | "credentials"
    # Vault label for vault grants; empty string for vocabulary-level grants
    resource_id: schema.String = field(
        default_factory=lambda: schema.String("")
    )
    # CRUD bitflag mask (READ|CREATE|UPDATE|DELETE) — vault grants only
    bits: schema.Integer | None = None
    # Scope level (read|mod|write|admin) — management grants only
    level: schema.String | None = None
