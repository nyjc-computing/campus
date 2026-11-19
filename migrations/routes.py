"""Per-service migration management routes (#1169).

The campus-admin Migrations view (campus-admin#75) drives the ratified
production migration loop (#1172): read the plan delta and ledger
history, trigger apply at a low-traffic window, abort between
migrations, roll back declared-capability revisions. The runner must
execute in each service's context (#1104 — the ledger lands in that
service's DB via its own POSTGRESDB_URI), so the surface is this small
blueprint mounted on EACH app service (campus.auth, campus.api,
campus.audit) under its management namespace:

    GET  /admin/migrations/          migrations:read
    POST /admin/migrations/apply     migrations:write
    POST /admin/migrations/abort     migrations:write
    POST /admin/migrations/rollback  migrations:admin

The blueprint is one factory shared by the three services; each
service's app init wires it next to its existing blueprint
registrations, passing its own authorization gate:

    migration_routes.init_app(app, service_db="auth", gate=gate, emit=emit)

- `service_db` — the runner scope ("auth" | "api" | "audit"); defaults
  to the DEPLOY-derived scope, exactly like runner.warn_if_pending.
- `gate(level)` — the per-service authorization callable; raises
  api_errors.ForbiddenError on denial. campus.auth passes the full
  two-leg store check (authz.require_resource_permission with the
  migrations vocabulary, instance = its own name). campus.api and
  campus.audit pass make_grant_check_gate() below.
- `emit(event, data)` — optional audit-yapper emitter for the mutating
  routes; the campus-admin surface must be attributable, so the service
  closure stamps the acting principal from flask.g before emitting.

Apply runs in a daemon thread (#1166 runner contract: the advisory
lock is the cross-worker guard, should_cancel is honored between
migrations); this module keeps a small process-local run-state holder
so GET can report `running` and a second apply/rollback in the same
process gets 409 instead of racing. The runner's stdout/stderr is
captured and logged to the service log — the route returns 202 long
before any output exists.

Rollback is synchronous (#1170 runner contract): single-shot, run in
the request thread, refused with 409 while an apply is in flight.

Authorization split (#1168, ratified): migrations:read < write < admin,
grant rows instance-scoped by resource_id in {"auth", "api", "audit"}.
The grant store lives only in campus.auth's database, so the api/audit
services settle the DESIGNATION leg over the mesh: an authenticated
server-to-server GET /grants/check (migrations vocabulary only, per
the #1168 service leg) using the service's OWN client credentials —
allowlisted on the auth deployment via AUTH_GRANT_CHECK_CLIENT_IDS.
The CAPABILITY leg (#1183) reads the bearer's scopes from
flask.g.current_scopes (hydrated by the shared Authenticator from
POST /root/authenticate's `scopes` field); scopes-less contexts —
audit API keys, or an auth deployment predating #1183 — fail closed
with a 403 naming the missing leg.
"""

__all__ = [
    "LEVEL_ADMIN",
    "LEVEL_READ",
    "LEVEL_WRITE",
    "create_blueprint",
    "init_app",
    "make_grant_check_gate",
    "resolve_service_db",
]

import ast
import contextlib
import hashlib
import io
import logging
import threading
from collections.abc import Callable
from pathlib import Path

import flask

import campus.flask_campus as flask_campus
from campus.common.errors import api_errors

logger = logging.getLogger(__name__)

# Vocabulary levels (#1168), low to high. GET reads at LEVEL_READ;
# apply/abort mutate at LEVEL_WRITE; rollback at LEVEL_ADMIN.
LEVEL_READ = "read"
LEVEL_WRITE = "write"
LEVEL_ADMIN = "admin"

# Where this service's ledger lives and which migrations it owns:
# the runner scope (#1104). Derived from DEPLOY exactly like
# runner.warn_if_pending; per-service wiring passes its own name
# explicitly (the wiring module IS the service, so the value is
# static and test-safe).
SERVICE_DBS = ("auth", "api", "audit")

# Runner imports are deferred into the helpers so that importing this
# module never initializes storage or reads the migrations directory:
# suite test processes import service apps whose init_app registers
# this blueprint long before any request arrives.


def resolve_service_db() -> str:
    """This service's runner scope, derived from DEPLOY (#1104).

    Same resolution as runner.warn_if_pending: DEPLOY names the
    deployment ("campus.auth" -> "auth"); contexts without DEPLOY
    (tests, ad-hoc scripts) fall back to the historical auth scope.
    """
    from campus.common import env
    from migrations import runner

    return runner.DEPLOY_TO_TARGET_DB.get(
        env.get("DEPLOY", "") or "", runner.DEFAULT_TARGET_DB
    )


# ---------------------------------------------------------------------------
# Run-state holder: process-local view of in-flight applies. The
# runner's advisory lock is the cross-worker guard (#1166); this holder
# is what turns "a second apply in the same process" into a 409 and
# what lets GET report `running` (the ledger alone cannot show
# in-flight).
# ---------------------------------------------------------------------------


class _ApplyRun:
    """One in-flight apply: its thread, cancel event and scope."""

    def __init__(self, service_db: str, thread: threading.Thread,
                 cancel_event: threading.Event):
        self.service_db = service_db
        self.thread = thread
        self.cancel_event = cancel_event


class _RunState:
    """Registry of in-flight applies, keyed by runner scope."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runs: dict[str, _ApplyRun] = {}

    def is_running(self, service_db: str) -> bool:
        with self._lock:
            run = self._runs.get(service_db)
            return run is not None and run.thread.is_alive()

    def start(self, service_db: str, target: Callable[[], None],
              cancel_event: threading.Event) -> _ApplyRun:
        """Start an apply thread for the scope; 409 if one is running.

        The registry entry is claimed BEFORE the thread starts, so two
        rapid-fire POSTs cannot both slip past the check. The cancel
        event is created by the caller (whose runner invocation reads
        it) and shared with the registry, so abort() pulls the same
        thread's brake.
        """
        with self._lock:
            run = self._runs.get(service_db)
            if run is not None and run.thread.is_alive():
                raise api_errors.ConflictError(
                    f"An apply is already running for the '{service_db}' "
                    "migration scope in this worker — poll GET "
                    "/admin/migrations/ for status; the runner's advisory "
                    "lock guards other workers"
                )
            thread = threading.Thread(
                target=self._wrap_target(service_db, target),
                name=f"migrations-apply-{service_db}",
                daemon=True,
            )
            entry = _ApplyRun(service_db, thread, cancel_event)
            self._runs[service_db] = entry
        thread.start()
        return entry

    def _wrap_target(self, service_db: str,
                     target: Callable[[], None]) -> Callable[[], None]:
        """Run the target and drop the registry entry when it exits."""

        def wrapped() -> None:
            try:
                target()
            finally:
                with self._lock:
                    self._runs.pop(service_db, None)

        return wrapped

    def abort(self, service_db: str) -> bool:
        """Set the cancel event; False when nothing is running (409).

        Cooperative (#1166): the hook is checked between migrations, so
        the in-flight migration finishes and the rest stay pending.
        """
        with self._lock:
            run = self._runs.get(service_db)
            if run is None or not run.thread.is_alive():
                return False
            run.cancel_event.set()
            return True


_RUN_STATE = _RunState()


def _capture_runner_output(action: Callable[[], int]) -> tuple[int, str]:
    """Run a runner command, capturing its printed output for the log.

    The runner reports progress by printing (CLI heritage); inside the
    app stdout is no one's console, so both streams are captured and
    returned for structured logging. Returns (exit_code, output).
    """
    out = io.StringIO()
    err = io.StringIO()
    code = 1
    try:
        with (contextlib.redirect_stdout(out),
              contextlib.redirect_stderr(err)):
            code = action()
    except Exception as exc:  # noqa: BLE001 - the thread must not die silently
        print(f"{type(exc).__name__}: {exc}", file=err)
        logger.exception("migrations runner raised in background thread")
    return code, (out.getvalue() + err.getvalue())


def _log_runner_output(prefix: str, code: int, output: str) -> None:
    """Log captured runner output, WARNING when the run failed."""
    text = output.strip() or "(no output)"
    log = logger.info if code == 0 else logger.warning
    log("%s: exit %s — %s", prefix, code, text)


# ---------------------------------------------------------------------------
# Ledger reads and migration-file metadata (read-only; the runner owns
# all writes).
# ---------------------------------------------------------------------------


def _connect_ledger():
    """Open the ledger connection (the service's own Postgres).

    Delegates to the runner's connection — same resolution path
    (POSTGRESDB_URI / vault getsecret), same ledger. Which DB that IS
    depends on the service context (#1104).
    """
    from migrations import runner

    return runner._connect()


def _fetch_history_rows() -> list[dict]:
    """All ledger rows in this service's DB, JSON-friendly.

    The per-DB ledger (#1104) is the service's migration history —
    including rows recorded before #1104 scoping that target other
    revisions' eras. A missing ledger table (fresh environment) reads
    as no history, mirroring runner status. Rows carry revision,
    filename, status, applied_at (ISO string), applied_by, duration_ms,
    error and file_hash — the #746 execution-audit columns.
    """
    # psycopg2 mirrors the runner's lazy import (no import-time
    # dependency beyond the call path that already needs the ledger);
    # the runner is the first-party connection + ledger owner.
    import psycopg2

    from migrations import runner

    conn = _connect_ledger()
    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f'SELECT revision, filename, status, applied_at, '
                    f'applied_by, duration_ms, error, file_hash '
                    f'FROM "{runner.LEDGER_TABLE}"'
                )
            except psycopg2.Error as e:
                if getattr(e, "pgcode", None) == runner.UNDEFINED_TABLE_SQLSTATE:
                    conn.rollback()
                    return []
                raise
            rows = cursor.fetchall()
    finally:
        conn.close()
    return [
        {
            "revision": row[0],
            "filename": row[1],
            "status": row[2],
            "applied_at": row[3].isoformat() if row[3] else None,
            "applied_by": row[4],
            "duration_ms": int(row[5]) if row[5] is not None else None,
            "error": row[6],
            "file_hash": row[7],
        }
        for row in rows
    ]


def _read_module_meta(path: Path) -> tuple[str | None, str | None]:
    """(rollback declaration, docstring summary) of a migration file.

    Parsed from the AST, never imported: importing executes a
    migration's top-level code (storage imports), which a GET route
    must not require — the same rule the runner's TARGET_DB reader
    follows. `rollback` is the ROLLBACK_SUPPORTED declaration
    ("ddl" | "backup" | None, #1170); `summary` is the module
    docstring's first line.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rollback = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "ROLLBACK_SUPPORTED"
                and isinstance(node.value, ast.Constant)):
            rollback = str(node.value.value)
            break
    docstring = ast.get_docstring(tree)
    summary = docstring.strip().splitlines()[0] if docstring else None
    return rollback, summary


def _file_hash(path: Path) -> str | None:
    """sha256 hexdigest of a migration file; None when unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _build_status_payload(service_db: str) -> dict:
    """The GET response body: scope, diff, plan, history, running."""
    from migrations import runner

    all_files = runner.discover_migration_files()
    files = runner.filter_files_by_db(all_files, service_db)
    history = _fetch_history_rows()
    rows = {row["revision"]: row for row in history}
    status = runner.compute_status(
        files, rows, known_revisions={f.revision for f in all_files}
    )
    plan = []
    for file in files:
        if rows.get(file.revision, {}).get("status") in (
                runner.APPLIED, runner.HISTORICAL):
            continue
        rollback, summary = _read_module_meta(
            runner.MIGRATIONS_DIR / file.filename
        )
        plan.append({
            "revision": file.revision,
            "filename": file.filename,
            "hash": _file_hash(runner.MIGRATIONS_DIR / file.filename),
            "rollback": rollback,
            "summary": summary,
        })
    return {
        "service": service_db,
        "status": [
            {"revision": file.revision, "filename": file.filename,
             "state": state}
            for file, state in status
        ],
        "plan": plan,
        "history": history,
        "running": _RUN_STATE.is_running(service_db),
    }


# ---------------------------------------------------------------------------
# The shared blueprint factory.
# ---------------------------------------------------------------------------


def create_blueprint(*, service_db: str | None = None,
                     gate: Callable[[str], None],
                     emit: Callable[[str, dict], None] | None = None,
                     ) -> flask.Blueprint:
    """Build the /admin/migrations blueprint for one service.

    Args:
        service_db: The runner scope ("auth" | "api" | "audit").
            Defaults to the DEPLOY-derived scope (resolve_service_db).
        gate: Authorization callable, called with the required
            vocabulary level ("read" | "write" | "admin"); raises
            api_errors.ForbiddenError on denial.
        emit: Optional audit/yapper emitter for the mutating routes,
            called as emit(event, data) inside the request context so
            the closure can stamp the acting principal from flask.g.

    Returns:
        The blueprint (url_prefix="/admin/migrations"), ready to
        register under the service's own namespace — each service's
        namespace prefixes it (/auth/v1, /api/v1, /audit/v1), and the
        blueprint-level authentication of that service applies.
    """
    if service_db is None:
        service_db = resolve_service_db()
    if service_db not in SERVICE_DBS:
        raise ValueError(
            f"service_db must be one of {', '.join(SERVICE_DBS)}, "
            f"got {service_db!r}"
        )
    bp = flask.Blueprint("migrations", __name__,
                         url_prefix="/admin/migrations")

    def _emit_event(event: str, data: dict) -> None:
        if emit is not None:
            with contextlib.suppress(Exception):
                emit(event, data)

    @bp.get("/")
    def get_status() -> flask_campus.JsonResponse:
        """Migration plan and ledger status for this service

        The plan delta and history the campus-admin Migrations view
        renders (#1172): the compute_status diff, per-file approval
        metadata (sha256, declared rollback support, docstring
        summary) for every pending revision, the full ledger history
        (who/when/duration/hash/error per the #746 execution audit),
        and whether an apply is in flight.

        GET /admin/migrations/
        Authorization: a principal holding the 'migrations:read'
        scope for this service (#1168: grant rows are instance-scoped
        by resource_id naming the service DB).

        Returns: {
            "service": <db>,
            "status": [{revision, filename, state}, ...],
            "plan": [{revision, filename, hash, rollback, summary}, ...],
            "history": [{revision, filename, status, applied_at,
                         applied_by, duration_ms, error, file_hash}, ...],
            "running": bool
        }

        Responses:
            200 OK: dict — the body above.
            403 Forbidden: dict — the caller fails the migrations
                gate for this service.
        """
        gate(LEVEL_READ)
        return _build_status_payload(service_db), 200

    @bp.post("/apply")
    @flask_campus.unpack_request
    def apply_migrations(
            *, up_to: str | None = None) -> flask_campus.JsonResponse:
        """Apply pending migrations (background)

        Starts the runner's apply for this service's scope in a
        background thread and returns immediately: one POST per
        staged window, progress lands in the service log and the
        ledger, and GET /admin/migrations/ polls `running`/`history`.
        The runner's advisory lock (#1166) guards other workers; an
        in-process second apply (or a rollback) gets 409. Cancel
        between migrations via POST /admin/migrations/abort.

        POST /admin/migrations/apply
        Authorization: a principal holding 'migrations:write' for
        this service (#1168).

        Body: {
            "up_to": "008"  (optional — apply only revisions at or
                            below this one; staged windows)
        }

        Returns: {"started": true, "service": <db>}

        Responses:
            202 Accepted: dict — the apply thread started.
            400 Bad Request: dict — unknown `up_to` revision.
            403 Forbidden: dict — the caller fails the migrations
                gate for this service.
            409 Conflict: dict — an apply is already running in this
                worker.
        """
        gate(LEVEL_WRITE)
        from migrations import runner

        if up_to is not None:
            try:
                runner.resolve_scoped_revision(
                    up_to, runner.discover_migration_files(), service_db
                )
            except ValueError as e:
                raise api_errors.InvalidRequestError(str(e)) from None
        argv = ["--db", service_db, "apply"]
        if up_to is not None:
            argv += ["--up-to", up_to]
        cancel_event = threading.Event()

        def target() -> None:
            code, output = _capture_runner_output(
                lambda: runner.main(argv, should_cancel=cancel_event.is_set),
            )
            _log_runner_output(
                f"migrations apply [{service_db}]"
                + (f" up_to={up_to}" if up_to else ""),
                code, output,
            )

        _RUN_STATE.start(service_db, target, cancel_event=cancel_event)
        _emit_event("campus.migrations.apply", {
            "service": service_db,
            "up_to": up_to,
        })
        logger.info(
            "migrations apply started [%s]%s",
            service_db, f" up_to={up_to}" if up_to else "",
        )
        return {"started": True, "service": service_db}, 202

    @bp.post("/abort")
    def abort_apply() -> flask_campus.JsonResponse:
        """Abort a running apply (between migrations)

        Sets the apply's cooperative cancel event (#1166): the hook
        is checked between migrations, so the in-flight migration
        finishes atomically and the remaining revisions stay pending
        (the next apply resumes them). 409 when nothing is running.

        POST /admin/migrations/abort
        Authorization: a principal holding 'migrations:write' for
        this service (#1168).

        Returns: {"aborting": true}

        Responses:
            200 OK: dict — the cancel event is set.
            403 Forbidden: dict — the caller fails the migrations
                gate for this service.
            409 Conflict: dict — no apply is running for this
                service.
        """
        gate(LEVEL_WRITE)
        if not _RUN_STATE.abort(service_db):
            raise api_errors.ConflictError(
                f"No apply is running for the '{service_db}' migration "
                "scope in this worker — nothing to abort"
            )
        _emit_event("campus.migrations.abort", {"service": service_db})
        logger.info("migrations abort requested [%s]", service_db)
        return {"aborting": True}, 200

    @bp.post("/rollback")
    @flask_campus.unpack_request
    def rollback_migration(
            *, revision: str,
            from_backup: str | None = None,
    ) -> flask_campus.JsonResponse:
        """Roll back one applied migration (synchronous)

        Delegates to the runner's rollback (#1170): migrations
        declaring ROLLBACK_SUPPORTED='ddl' run their downgrade();
        'backup' migrations restore the envelope named by
        `from_backup` (a local path or a bucket://<name>/<key> URI —
        the apply's fail-closed backup upload is where the URI comes
        from). Undeclared revisions, hash-guarded files and held
        advisory locks are refused by the runner; on any failure the
        ledger row stays applied. Refused with 409 while an apply is
        in flight.

        POST /admin/migrations/rollback
        Authorization: a principal holding 'migrations:admin' for
        this service (#1168 — the destructive cap, granted
        sparingly).

        Body: {
            "revision": "007",
            "from_backup": "bucket://campus-backups/migrations/005/..."
                           (required for backup-restoration
                           migrations)
        }

        Returns: {"rolled_back": <revision>}

        Responses:
            200 OK: dict — the revision is pending again.
            400 Bad Request: dict — unknown revision (or a backup
                rollback invoked without from_backup).
            403 Forbidden: dict — the caller fails the migrations
                gate for this service.
            409 Conflict: dict — the revision is not applied, cannot
                be rolled back, is hash-guarded, a run holds the
                advisory lock, or an apply is in flight in this
                worker; the message carries the runner's error text.
        """
        gate(LEVEL_ADMIN)
        from migrations import runner

        if _RUN_STATE.is_running(service_db):
            raise api_errors.ConflictError(
                f"An apply is running for the '{service_db}' migration "
                "scope in this worker — abort or wait for it to finish "
                "before rolling back"
            )
        try:
            runner.resolve_scoped_revision(
                revision, runner.discover_migration_files(), service_db
            )
        except ValueError as e:
            raise api_errors.InvalidRequestError(str(e)) from None
        argv = ["--db", service_db, "rollback", revision]
        if from_backup:
            argv += ["--from-backup", from_backup]
        code, output = _capture_runner_output(
            lambda: runner.main(argv)
        )
        _log_runner_output(
            f"migrations rollback [{service_db}] revision={revision}",
            code, output,
        )
        if code != 0:
            # The runner's failure classes are ledger-state conflicts
            # (not applied, undeclared rollback, hash guard, held
            # advisory lock) — 409 with its error text; the full
            # output is in the service log above.
            raise api_errors.ConflictError(
                f"Rollback of {revision} failed — see the service log "
                "for the runner output"
            )
        _emit_event("campus.migrations.rollback", {
            "service": service_db,
            "revision": revision,
            "from_backup": from_backup,
        })
        return {"rolled_back": revision}, 200

    return bp


def init_app(app: flask.Flask | flask.Blueprint, *,
             service_db: str | None = None,
             gate: Callable[[str], None],
             emit: Callable[[str, dict], None] | None = None,
             ) -> None:
    """Register the migrations blueprint on a service app/blueprint.

    Convenience over create_blueprint for services that register
    blueprints directly; campus.audit attaches its API-key
    authentication per blueprint and uses create_blueprint instead.
    """
    app.register_blueprint(create_blueprint(
        service_db=service_db, gate=gate, emit=emit,
    ))


# ---------------------------------------------------------------------------
# The api/audit designation gate (#1168 service leg).
# ---------------------------------------------------------------------------


def _principal_user_id() -> str | None:
    """The authenticated user principal's id, if the caller is a user.

    campus.api's middleware hydrates the authenticate result's user
    into a campus.model.User object; some test doubles carry a plain
    dict — handle both (the api authz module's convention). Audit API
    keys set no user principal at all.
    """
    user = getattr(flask.g, "current_user", None)
    value = (
        user.get("id") if isinstance(user, dict)
        else getattr(user, "id", None)
    )
    return str(value) if value else None


_grant_check_client_cache: list = []


def _grant_check_client():
    """The deployment's own campus.auth client, created once.

    The #1168 service leg authenticates with the service's own client
    credentials (CLIENT_ID/CLIENT_SECRET env — the server-mode SDK
    sends HTTP Basic), so campus.auth resolves the calling client and
    matches it against AUTH_GRANT_CHECK_CLIENT_IDS. Created lazily:
    audit service tests construct apps without app credentials, and
    the gate must not pay for an SDK client it never calls.
    """
    if not _grant_check_client_cache:
        import campus_python

        _grant_check_client_cache.append(campus_python.Campus().auth)
    return _grant_check_client_cache[0]


def _check_grant_remotely(client_getter: Callable[[], object] | None,
                          **query) -> bool:
    """GET /grants/check over the mesh; per-request cached (flask.g).

    No cross-request caching: grants must revoke immediately (#1169).
    The auth deployment allowlists this service's client id via
    AUTH_GRANT_CHECK_CLIENT_IDS for migrations checks (#1168) — a 403
    from the check is an ops-config gap and surfaces as the actionable
    ForbiddenError; any other failure to reach campus.auth fails
    closed as ServiceUnavailableError.
    """
    from campus_python import errors as client_errors

    cache = getattr(flask.g, "_migrations_grant_checks", None)
    if cache is None:
        cache = {}
        flask.g._migrations_grant_checks = cache
    key = tuple(sorted(query.items()))
    if key not in cache:
        client = client_getter() if client_getter else _grant_check_client()
        try:
            cache[key] = bool(client.grants.check(**query))
        except client_errors.AccessDeniedError as e:
            from campus.auth.authz import GRANT_CHECK_CLIENT_IDS_ENVVAR

            raise api_errors.ForbiddenError(
                "campus.auth refused the migrations grant check "
                f"({GRANT_CHECK_CLIENT_IDS_ENVVAR}): add this "
                "deployment's client id to that allowlist on the "
                "campus.auth deployment (#1168 service leg)"
            ) from e
        except Exception as e:  # noqa: BLE001 - fail closed on any check failure
            if isinstance(e, api_errors.ForbiddenError):
                raise
            logger.warning("migrations grant check failed: %s: %s",
                           type(e).__name__, e)
            raise api_errors.ServiceUnavailableError(
                "The migrations designation check could not reach "
                "campus.auth — failing closed; retry when the auth "
                "service is reachable"
            ) from None
    return cache[key]


def make_grant_check_gate(service_db: str, *,
                          client_getter: Callable[[], object] | None = None,
                          check_grant: Callable[..., bool] | None = None,
                          principal_description: str = (
                              "Client principals (and audit API keys)"),
                          ) -> Callable[[str], None]:
    """The api/audit authorization gate for the migrations routes.

    The ratified two-leg split (#1168, #1169) as it applies off the
    auth service:

    - DESIGNATION leg: a grant row in campus.auth's access-grant store
      covering `migrations:<level>` with resource_id=<service_db> —
      settled over the mesh via GET /grants/check (the #1168 service
      leg: migrations vocabulary only, caller allowlisted by
      AUTH_GRANT_CHECK_CLIENT_IDS), using this service's OWN client
      credentials (_designation_leg_holds).
    - CAPABILITY leg: the caller's bearer carrying the
      migrations:<level> scope (#1183): `flask.g.current_scopes` is
      hydrated by the shared Authenticator from POST
      /root/authenticate's `scopes` field (campus.api passes the
      field through; the algebra is mirrored in _scope_grants — do
      not import the campus.auth package here). Scopes-less contexts
      fail closed: audit API keys are not campus bearers, and an auth
      deployment predating #1183 surfaces no scopes.

    Args:
        service_db: This service's grant instance ("api" | "audit").
        client_getter: Optional zero-arg callable returning the
            campus.auth SDK client for the check (campus.api passes
            its shared Campus().auth so the call rides the traced
            session); the default builds one lazily.
        check_grant: Optional direct replacement for the designation
            leg — tests inject fakes with this signature:
            check_grant(**query) -> bool.
        principal_description: Names the non-user principals in the
            denial message (audit keys vs plain clients).

    Returns:
        gate(level) — raises api_errors.ForbiddenError on denial.
    """
    # The capability leg (#1183): the request context carries the
    # bearer's granted scopes (flask.g.current_scopes, hydrated by the
    # shared Authenticator from POST /root/authenticate's `scopes`
    # field — campus.api passes the field through). Audit API keys and
    # any deployment pair where auth has not yet been upgraded carry no
    # scopes here: the check fails closed, exactly as before #1183.
    def gate(level: str) -> None:
        user_id = _principal_user_id()
        if user_id is None:
            raise api_errors.ForbiddenError(
                f"{principal_description} hold no 'migrations' "
                "authority (#854/#1169): the migration management "
                "routes accept a designated user's campus bearer; "
                "settle the user's migrations grant via the campus.auth "
                "grant store"
            )
        held = getattr(flask.g, "current_scopes", None) or []
        if not _scope_grants(held, f"migrations:{level}"):
            # Capability leg, fail-closed (#865: designation without
            # the scope must never confer authority — the exact
            # regression #854 closed). No campus scopes in the request
            # context = denial: audit API keys are not campus bearers,
            # and an auth deployment predating #1183 surfaces no
            # scopes to its services.
            raise api_errors.ForbiddenError(
                f"Token lacks 'migrations:{level}' (#865, #1183): a "
                "designated user must hold the management scope on "
                "the bearer as well as the grant row — mint the token "
                "through a client whose allowed_scopes includes the "
                "migrations vocabulary; a scope-less context (audit "
                "API keys, or an auth deployment predating #1183) "
                "fails closed"
            )
        if not _designation_leg_holds(
                user_id, level, service_db,
                client_getter=client_getter, check_grant=check_grant,
        ):
            raise api_errors.ForbiddenError(
                f"No access grant designates this user for "
                f"'migrations:{level}' on '{service_db}' (#1168): "
                "designated authority is administered via the "
                "campus.auth access-grant store"
            )

    return gate


# The management-scope level algebra, mirrored from campus.auth.scopes
# (#1183): routes.py is shared by every service and must NOT import
# the campus.auth package (its module init registers auth's vault
# getsecret handler on the importing service). Keep in lockstep with
# campus.auth.scopes._SCOPE_LEVELS / scopes.grants.
_SCOPE_LEVELS = {"read": 0, "mod": 1, "write": 2, "admin": 3}


def _scope_grants(held: list[str], required: str) -> bool:
    """True if the held scopes confer `required` (monotonic levels).

    `<resource>:<admin>` implies write implies read on the same
    resource; unknown levels fail closed.
    """
    resource, _, level = required.partition(":")
    required_rank = _SCOPE_LEVELS.get(level)
    if required_rank is None:
        return False
    for scope in held:
        scope_resource, _, scope_level = scope.partition(":")
        if scope_resource != resource:
            continue
        if _SCOPE_LEVELS.get(scope_level, -1) >= required_rank:
            return True
    return False


def _designation_leg_holds(user_id: str, level: str, service_db: str, *,
                           client_getter: Callable[[], object] | None = None,
                           check_grant: Callable[..., bool] | None = None,
                           ) -> bool:
    """The designation leg of the api/audit gate (#1168 service leg).

    True when campus.auth's access-grant store holds a migrations row
    for this user on this service whose level covers `level`. The
    check result is cached per request only (flask.g) — grants must
    revoke immediately, never across requests.
    """
    if check_grant is not None:
        return bool(check_grant(
            grantee_type="user",
            grantee_id=user_id,
            resource_type="migrations",
            resource_id=service_db,
            level=level,
        ))
    return _check_grant_remotely(
        client_getter,
        grantee_type="user",
        grantee_id=user_id,
        resource_type="migrations",
        resource_id=service_db,
        level=level,
    )
