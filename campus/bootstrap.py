"""campus.bootstrap

Shared startup storage-initialization policy for the suite services.

The storage layer blocks `init_from_model` in production
(@env.block_env(PRODUCTION) in campus-core): production schema is owned
by migrations/ and the out-of-band bootstrap
(`python scripts/init_storage.py --service <svc>`), never by app
startup. Every service whose startup calls `init_storage()` therefore
needs the same two-part convention (#1103):

1. Skip initialization in production (the storage layer would raise,
   crash-looping the deployment — campus.audit's first prod boot did
   exactly that, #1100).
2. Outside production, run it self-healing: idempotent
   CREATE TABLE IF NOT EXISTS / collection setup, loud but non-fatal on
   failure, with the recovery path spelled out in the log line.

`run_init_storage` is that convention, stated once. Service startup
paths (campus.auth._init_auth_tables, campus.api._init_api_tables,
campus.audit.init_app) route every guarded init through it, so a new
resource's init inherits correct behavior by construction instead of by
copy-paste.
"""

__all__ = ["run_init_storage"]

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def run_init_storage(init_fn: Callable[[], None], *,
                     what: str, recovery: str) -> None:
    """Run one startup storage init under the self-heal convention.

    Args:
        init_fn: Zero-argument callable performing the idempotent
            initialization (a resource's init_storage or a small
            wrapper combining related calls).
        what: What is being initialized, phrased for an operator,
            e.g. "the school calendar table".
        recovery: How to create the table/collection out-of-band when
            startup skipped or failed, phrased as a command or pointer,
            e.g. "python scripts/init_storage.py --service api".

    In production this logs (at debug) that initialization was skipped
    and never calls init_fn — the storage layer blocks init_from_model
    there, and schema is owned by migrations/ plus the out-of-band
    bootstrap. Anywhere else, init_fn runs inside a catch-all that
    logs the failure loudly with the recovery path and returns without
    raising: a broken init must not take down the rest of startup
    (other resources, seeding, blueprint registration), and a missing
    table surfaces at request time with its own error.
    """
    from campus.common import env

    if env.ENV == env.PRODUCTION:
        logger.debug(
            "ENV=production: skipping startup storage init for %s "
            "(schema is managed by migrations/ and "
            "scripts/init_storage.py, not app startup)",
            what,
        )
        return
    try:
        init_fn()
    except Exception:
        logger.exception(
            "Failed to initialize %s. Recover: %s", what, recovery
        )
