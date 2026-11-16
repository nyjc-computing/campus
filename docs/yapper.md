# campus.yapper — event bus

`campus.yapper` is Campus's event bus: services emit domain events
(`auth` emits `campus.oauth.token`, `campus.clients.create`, …; `api`
emits submission/assignment/circle events), and clients subscribe and
handle them. Events are persisted in a dedicated event database
(`yapperdb`): PostgreSQL in deployments, a SQLite file in tests.

This guide covers how to obtain and use a yapper client. For the label
naming convention (shared with journey names, see
[audit-tracing.md](audit-tracing.md)), and for the consumer middleware
that relates emissions to journeys, see the audit tracing doc.

## Self-contained by contract

`campus.yapper` imports **no other campus package** — not even
`campus.common`. This is enforced by the boundary contract
(`tests/unit/test_package_boundaries.py`, `SHARED_ALLOWED["yapper"]`
is empty). The reason is historical: yapper used to lazily import
`campus.auth.resources` to read its database URI from the vault,
forming a lazy `yapper ↔ auth` import cycle (#970 phase 2 removed it).

The practical consequence: **all configuration arrives through
arguments or environment variables.** If a caller has local secret
access (like the auth service reading its own vault), it passes that
access in as a callable instead of yapper reaching into campus.auth.

## Getting a client: `campus.yapper.create()`

The event database URI is resolved in priority order:

| Priority | Source | Notes |
|---|---|---|
| 1 | `db_uri=` argument | Explicit, highest priority |
| 2 | `db_uri_provider()` callable | For callers with local vault access |
| 3 | `YAPPERDB_URI` environment variable | Used by bare `create()` in tests |
| 4 | Remote campus vault `"campus.yapper"` via campus_python | Default for service deployments |

Client identity always comes from the environment: `CLIENT_ID` and
`CLIENT_SECRET` are required. The backend is `SQLiteYapper` when
`STORAGE_MODE=1` (test mode) and `PostgreSQLYapper` otherwise.

### Emitters without local vault access (api-style)

```python
import campus.yapper

yapper = campus.yapper.create()  # creds + vault via environment/SDK
yapper.emit("campus.submissions.submit", {"assignment_id": aid})
```

No arguments needed: credentials come from `CLIENT_ID`/`CLIENT_SECRET`,
and the database URI is fetched from the remote `"campus.yapper"` vault
through campus_python.

### Callers with local vault access (the auth service)

A service must not call its own HTTP API during initialization, so the
auth service injects a provider backed by its in-process vault instead
of letting yapper read it (see `campus.auth.get_yapper`):

```python
import campus.yapper
from .resources import vault

yapper = campus.yapper.create(
    db_uri_provider=lambda: vault["campus.yapper"]["YAPPERDB_URI"]
)
```

### Tests

Test fixtures seed the vault secret **and** export it as the
`YAPPERDB_URI` environment variable (see `tests/fixtures/yapper.py`);
bare `create()` calls then resolve via priority 3. Test mode
(`STORAGE_MODE=1`) never contacts external services: with no URI
resolvable from arguments, provider, or environment, `create()` raises
`ValueError` rather than reaching the remote vault.

### Removed: the `DEPLOY=campus.auth` special case

Earlier versions made yapper read the local auth vault itself whenever
`DEPLOY=campus.auth` was set. That branch is gone — auth now passes the
`db_uri_provider` explicitly (above), and yapper no longer consults the
`DEPLOY` variable. No environment changes are needed; the wiring is in
code.

## Emitting and handling events

```python
yapper.emit("campus.users.create")                       # no payload
yapper.emit("campus.clients.update", {"client_id": cid}) # with payload

@yapper.on_event("campus.clients.update")
def handle(event) -> None:
    ...
```

Labels follow the `campus.<subject>[.<sub>].<action>` namespace, which
is shared with journey names. Handlers receive an `Event` (`.label`,
`.data`); `yapper.run()` polls the backend and dispatches to registered
handlers (`start()`/`stop()` control the loop, `listen()` returns raw
events, `subscribe()`/`unsubscribe()` manage label subscriptions).

## Vault contract

The event database URI lives as a secret (`YAPPERDB_URI`) in the
`"campus.yapper"` vault, managed by campus.auth with normal client
access grants (see `tests/fixtures/yapper.py` for how test clients are
granted access). The vault delivery contract is covered by
`tests/integration/yapper/test_yapper.py`. Clients should not assume
*how* a yapper instance obtained its URI — only the resolution order
above.
