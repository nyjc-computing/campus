---
name: railway-ops
description: >-
  Traps and recipes for the Railway CLI/GraphQL API and Railway private
  networking in this project — service config mutations (schema changed),
  triggering redeploys, deleting services, deploy queueing, IPv6-only mesh
  requirements, in-deployment observability/probing (replica id, CPU/RAM,
  instance discovery), and Windows shell quirks. Use when touching Railway
  services (vars, domains, healthchecks, start commands, replica counts),
  debugging gateway/upstream failures, waiting on deployments, or measuring
  a deployment from inside it.
---

# Railway ops (campus project)

Project: `76e0b6d0-0832-41dc-841f-e3bc758d3eca`. Environments: `development`
(e954f5fa…, weekly autodeploys here — all testing happens here),
`production`
(d5221f3b…, deploys from `main` — the weekly → main release PR is the
only path to `main`; cutover completed 2026-11-17). Two environments
only: `staging`/`production-legacy` and the `staging` git branch +
ruleset were all deleted 2026-11-17 (campus#1122). `railway status
--json` lists them with
`environments.edges[].node.serviceInstances.edges[].node` carrying
`serviceName`, `serviceId`, `startCommand`, `activeDeployments`.

## Access model (2026-11-17 policy — read before any Railway work)

- **Routine Railway access is environment-bound to `development`**:
  commands run with `RAILWAY_TOKEN` set to a development-scoped project
  token (`rlwy_proj_…`; machine file `~/.railway-dev-token`, exported
  into each Git Bash session by `~/.bashrc`). **Variable name matters**:
  project tokens only authenticate as `RAILWAY_TOKEN` — under
  `RAILWAY_API_TOKEN` (account keys) every command fails. Verified:
  `railway status` sees project `campus` / environment `development`
  only; production resolves as "not found"; account-level commands
  (`whoami`, `list`) are denied by design — **auth-check with
  `railway status`, never `whoami`** (a valid project token 401s
  `whoami` and looks dead when it isn't). Escape hatch for superadmin
  production work: `env -u RAILWAY_TOKEN railway <cmd>` (falls through
  to the personal login).
- **Token storage layout (rotated 2026-11-21 after a transcript leak;
  the old user-scope Windows env var `RAILWAY_TOKEN` was removed from
  HKCU and must NOT be re-created — it silently overrides the file
  export in non-bash processes and outlives rotations):**
  - dev: `~/.railway-dev-token` (project token for the campus dev
    environment; `~/.bashrc` exports it as `RAILWAY_TOKEN` per shell).
  - prod: `campus-prod/.railway-prod-token` and
    `campus-staging/.railway-prod-token` (per-directory, never
    exported). Use as
    `RAILWAY_TOKEN="$(cat .railway-prod-token)" railway <cmd>`.
    Project tokens carry their project/environment scope, so these
    resolve `campus`/`production` with no linked config. Both
    dirs share one token today; split them if prod/staging ever
    diverge again.
  - The parent `D:/nyjc-computing` repo's `.gitignore` carries
    `.railway-*-token` so `git add -A` sweeps can't commit them.
  - Token values are shown ONCE at creation in the dashboard; a
    re-copy of a stale dialog re-copies a dead value — always mint a
    fresh entry when a token stops authenticating (symptom:
    `Invalid RAILWAY_TOKEN` on every command including `status`).
    The creation dialog must ALSO be completed/dismissed before the
    token activates — a minted-but-unconfirmed token reads as invalid
    too (hit live 2026-11-23: the token was correct all along and
    started authenticating the moment the dialog was clicked through).
- **Production is superadmin-only**: logs, variables, domains, SSH,
  redeploys, and all production data. Do not point CLI/automation at
  production; deployment-side debugging there is a superadmin activity.
- Production data is never accessed directly (no ssh/tcp-proxy/db reads
  outside the documented bootstrap runbook in prod-rollout.md §3).
- Policy: docs/environment-access-policy.md.

## Private networking is IPv6-only — listeners must bind `[::]`

- A container bound to `0.0.0.0` (IPv4 only) is **unreachable over the mesh**;
  the failure surfaces at the caller as `ECONNREFUSED` on
  `http://[fd12:…]:PORT` (fast RST) or a silent established-then-stall hang.
- Flask services (gunicorn) must use `--bind [::]:$PORT` (dual-stack on
  Linux; keeps public IPv4 working). Applied to dev auth/api/audit
  2026-10-30; applied across the production fleet at the 2026-11-16/17
  rollout.
- MongoDB containers run `mongod --ipv6 --bind_ip ::,0.0.0.0` for the same
  reason (Railway's documented recipe).
- Known-good reference pairs: campus.auth → auth-mongodb.railway.internal and
  auth-postgres.railway.internal both work over the mesh.
- Doc set: docs.railway.com/networking/private-networking (+ /how-it-works,
  /library-configuration). Staff guidance: "listen on the `::` host"
  (station.railway.com/questions/cannot-connect-with-private-network-8a8572c5).

## GraphQL mutation schema (changed 2026-10 — old snippets online are stale)

- `serviceInstanceUpdate(environmentId:…, serviceId:…, input:{…})` — ids are
  TOP-LEVEL args now (projectId/environmentId/serviceId are NOT in the
  input), and it returns a bare `Boolean!` (no selection subfields).
  Input fields: startCommand, healthcheckPath, rootDirectory, watchPatterns,
  numReplicas, … (introspect `ServiceInstanceUpdateInput`).
- **`numReplicas` silently no-ops unless `multiRegionConfig` is set too**
  (hit 2026-11-24): the deployment manifest's
  `multiRegionConfig.<region>.numReplicas` (default 1) OVERRIDES the
  top-level `numReplicas` — the override is visible in `deployment.meta`
  (`deploy.multiRegionConfig`). Set BOTH: `input:{numReplicas:N,
  multiRegionConfig:$m}` with
  `--var m='{"asia-southeast1-eqsg3a":{"numReplicas":N}}'` (the hyphenated
  region key can't be a GraphQL object-literal key → must pass as a JSON
  variable; region id = `RAILWAY_REPLICA_REGION` inside any of the
  service's deployments). Verify with
  `deployment(id){ instances { id status } }` — one entry per live
  replica, and instance `id` == `RAILWAY_REPLICA_ID` as seen inside the
  guest.
- `serviceInstanceDeploy(environmentId:…, serviceId:…, latestCommit:true)` —
  explicitly triggers a deployment of the current config. **Config mutations
  do not always auto-trigger a deploy** (observed: of three identical
  startCommand updates, only one redeployed on its own; the other two needed
  this call).
- `serviceDomainDelete` also takes TOP-LEVEL args (no input wrapper); or use
  the CLI: `railway domain delete <DOMAIN_OR_ID> -s <svc> --yes`.
- `service delete` (CLI) is permission-refused in this workspace — delete
  services via the dashboard.

## In-deployment observability & probing (probed 2026-11-24)

Each replica boots its own microVM ("Booting VM for replica N" in the
deploy log; kernel `6.18.60-railway`) **sized to the service's instance
limits** — defaults are 32 vCPU / 32 GB / pidLimit 1000. The guest sees its
entitlement directly: `nproc` / `os.cpu_count()` == the vCPU limit,
`/proc/meminfo` == the memory limit. cgroup v2 exists
(`/workload/app.scope`) but the quota files (`cpu.max`, `memory.max` /
`memory.current` / `memory.peak`, `pids.*`) are EMPTY — Railway does not
enforce via cgroups. Set limits with
`serviceInstanceLimitsUpdate(input:{environmentId, serviceId, vCPUs,
memoryGB})`; read back with `serviceInstanceLimits` (returns
`containers:{cpu, memoryBytes, pidLimit}`).

- **Identity vars**: `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_REPLICA_ID`
  (present even at 1 replica), `RAILWAY_REPLICA_INCARNATION` (== hostname,
  `rep-<dep8>-<uid>-<idx>-<n>`), `RAILWAY_REPLICA_REGION`,
  `RAILWAY_SNAPSHOT_ID`. NO var exposes the instance count.
- **CPU%**: diff `/sys/fs/cgroup/cpu.stat` `usage_usec` across a wall-time
  window (idle fleet services sit at a few % of one core; boot churn reads
  much higher — sample after settle). `nr_throttled`/`throttled_usec` =
  starvation signal. RAM: `/proc/meminfo`, `VmRSS`,
  `memory.stat` anon/file. psutil is NOT in slim/python images — parse
  files.
- **Instance count**: in-guest, count unique AAAA records for
  `$RAILWAY_PRIVATE_DOMAIN` (`getent ahostsv6 … | sort -u`) — one per
  live replica, visible from t+5s on a fresh scale-out. Externally,
  `deployment(id){ instances { id status } }` (works with the dev project
  token); instance `id` == `RAILWAY_REPLICA_ID`.
- **Request arrival**: Railway's edge stamps `X-Request-Start` on every
  public request (Unix milliseconds; documented in Specs & Limits), on
  direct service domains too. Don't add a gateway `proxy_set_header` for
  it — that overwrites the edge value (#1242's stamp was reverted, #1243).
- **Serverless sleep**: a service sleeps 5–10 min after its last OUTBOUND
  packet (network requests, DB connections, even NTP) — CPU% is not the
  signal, and there is no documented CPU-based replica autoscaler (the
  replica count is a manual setting). Any timer that talks keeps it
  awake: background work goes in the cron-scheduled **campus-cleanup**
  deployment (`Dockerfile.cleanup`, batch job that talks to the service
  DBs directly and never calls the app services — docs/cleanup-deployment.md;
  native Railway cron, ≥5 min apart, `railway cron run` for a one-off)
  or rides on inbound requests (#1249).
- **Job SUCCESS ≠ job completion**: Railway marks a batch deployment
  SUCCESS when the container STARTS (observed live 2026-11-25 with the
  campus-migrate job mid-backfill). For long jobs, poll the deployment
  LOG for the runner's completion lines or the ledger — never the
  deployment status — and never redeploy the service while it runs:
  a new deployment STOPS the running one (cost: a killed 014 apply at
  ~8% done, redone from scratch — the migration was idempotent, which
  is why that ended in recovery, not damage).
- **Probing recipe** (`railway ssh` is BLOCKED from the office host —
  `ssh.railway.com:22` connection timeout even with a valid personal
  login; it's port filtering, not auth):
  1. `serviceCreate(input:{projectId, environmentId, name:"probe-tmp",
     source:{image:"python:3.13-slim"}, variables:{…}})` — image deploys
     skip the build entirely.
  2. `serviceInstanceUpdate(input:{startCommand:"/bin/sh -c \"echo <b64>
     | base64 -d | sh\"", restartPolicyType:NEVER})` — **the script must
     travel base64-encoded**: raw `$VAR`-style interpolation of a
     multi-line value in startCommand flattens the script to one line and
     it never executes (boot log shows the flattened text; hit live
     2026-11-24).
  3. `serviceInstanceDeploy(environmentId, serviceId, latestCommit:true)`,
     poll `activeDeployments[0]` (a probe that exits 0 lands SUCCESS or
     CRASHED — logs are readable either way by explicit deployment id:
     `railway logs <DEPLOYMENT_ID> -s probe-tmp -e development --lines N`).
  4. Cleanup: `deploymentRemove(id)` works via project token;
     `serviceDelete` is permission-refused for the workspace role —
     dashboard-delete the dormant service shell.

## Database bootstrap ordering — credentials BEFORE first boot (#1105)

- **Attaching a volume to a freshly-created DB service triggers a
  deployment.** The datadir initializes with whatever credentials exist
  at that moment; `variableUpsert` has `skipDeploys`, `volumeCreate`
  does not — credentials patched in after the boot are silently
  ignored (postgres initdb'd with generated passwords; mongo same).
  Every app URI composed against the intended passwords then fails
  auth. Safe order: create the service **with credentials in the
  creation payload** (`serviceCreate(variables=…)` / `railway add
  --variables "$(cat .tmp-vars.json)"`) → volume → start command →
  deploy. Verify connectivity (below) before wiring app URIs.
- **Postgres recovery** (`databasePasswordReset`, `databaseType:
  "postgres"`) rotates the role password — but its response's
  `updatedVariables.DATABASE_URL` contains a password **different from
  the actual `newPassword`** (verified 2026-11-16: only `newPassword`
  authenticates). Trust `newPassword`; fix the DB service's own
  `DATABASE_URL`/`PGPASSWORD` vars to the truth manually, then
  `${{…DATABASE_URL}}` references on consumers resolve correctly.
- **Mongo has no reset mutation.** Volume deletion is permission-refused
  for the workspace role (dashboard-only), so recovery is deleting the
  service (dashboard-only too) and recreating it with credentials in
  the creation payload.
- **Verification before wiring app URIs**: `railway tcp-proxy create
  -s <db-service> -p <port>`, ping with the INTENDED credentials
  (`psql "$DATABASE_URL" -c 'select 1;'` /
  `mongosh "$MONGODB_URI" --eval 'db.runCommand({ping: 1})'`), then
  `railway tcp-proxy delete` — always.

## Deploy queue and status checks

- Config-change deploys can sit `WAITING` ~4 min before `BUILDING`.
  Poll `activeDeployments[0]` per service (fields: `createdAt`, `status`,
  `meta.serviceManifest.deploy.startCommand`). Terminal: SUCCESS / CRASHED /
  SKIPPED / REMOVED. Expect ~5 min build+deploy for the Flask services.
- **A trigger can silently NOT deploy (#1106)**:
  `serviceInstanceDeploy(latestCommit)` can return true while the row is
  created SKIPPED and nothing ever materializes; later triggers keep
  no-oping while the stale deployment keeps serving. Always compare
  `createdAt` against the pre-trigger row — a "successful" trigger call
  proves nothing. `scripts/railway_deploy.sh <svc> <env>` does the whole
  trigger-verify-recover loop for you (records the old row, triggers via
  `railway redeploy --from-source`, polls for a NEW row, recovers a
  SKIPPED row with a plain redeploy of the active deployment, and times
  out loudly when no row materializes).
- A failed healthcheck keeps the OLD deployment live (rollback-safe changes).
- `railway logs -s <svc> -e development --lines N` streams deploy logs
  (nginx access+error lines land here).

## Healthchecks — set on every app service (#1107)

- App services run `healthcheckPath: /health` +
  `healthcheckTimeout: 10` (every service has the #842 `/health`
  route; it deliberately doesn't touch storage). Set on campus.auth,
  campus.api, campus.audit, campus-gateway in BOTH environments
  (2026-11-17). DB services stay restart-policy-only. A NEW app
  service must set this at creation — a service that boots but 500s on
  every request is otherwise indistinguishable from healthy, and a
  crash-looping deploy is invisible (the #1107 incident: audit's first
  prod boot crash-looped unnoticed; auth booted "SUCCESS" while
  broken).
- Recipe (ids via `railway status --json`; the mutation is a bare
  `Boolean!`, so no selection set):
  `railway api 'mutation($e:String!,$s:String!){ serviceInstanceUpdate(environmentId:$e, serviceId:$s, input:{healthcheckPath:"/health", healthcheckTimeout:10}) }' --var e=<envId> --var s=<svcId>`
- After any config change, trigger + verify with
  `scripts/railway_deploy.sh <svc> <env>` — a config change alone does
  not redeploy. With a healthcheck set, deploy SUCCESS means `/health`
  answered: "actually serving", not merely "container up".
- **Unsetting an instance `startCommand`** (handing the start command
  back to repo-derived config — Procfile/railpack): `startCommand: null`
  returns `true` but **silently does nothing** (hit 2026-11-26 dropping
  the downstream bind overrides, campus#1295 Phase 0 — readback still
  showed the old command). Set it to the **empty string** instead: that
  stores `''`, and the next deploy falls back to the repo's own start
  definition. Verify with the `serviceInstance{startCommand}` readback,
  then redeploy — with no healthcheck configured, SUCCESS means
  "container started", so also probe a real route.
- Deploy-failure **notifications** remain dashboard-only: the API's
  `notificationRuleCreate` takes an undocumented
  `NotificationChannelConfig` scalar (blind-guessing its JSON shape is
  how you email nobody) — Project Settings → Notifications, rule
  scoped to the production environment.

## Environments, ghosts, and cascade redeploys (#1109)

- **Never create an environment by duplicating one.** Duplication
  copies EVERY service — with the source environment's variables. The
  2026-11-16 prod standup was bitten twice by the resulting ghosts:
  they look like fleet members, hold dev secrets in prod-scoped vars,
  and `serviceCreate` refuses duplicate names, so a removed instance
  cannot be re-materialized by any API/CLI path. Policy: create
  services explicitly into the target environment
  (`serviceCreate(environmentId, …)`); duplication is reserved for
  app-env parity checks, followed by an inventory sweep.
- **Deleting or renaming a service cascade-redeploys every service
  holding its derived references** (`RAILWAY_SERVICE_*` vars, domain
  deletions): classroom and apphost silently STARTED themselves in
  prod from a rename cascade. Expect a redeploy wave after any
  entity-level delete/rename, and re-run `scripts/railway_env_audit.sh`
  afterwards — it lists both environments' instances and flags
  NEVER-DEPLOYED instances (the ghost signature) and prod members
  that are SLEEPING/STOPPED/CRASHED.
- Instance removal (vs entity deletion) is dashboard-only for the
  workspace role; serviceDelete likewise. Budget for the dashboard
  when cleaning up ghosts.

## CLI shell traps (Windows / Git Bash)

- `railway` cannot be spawned from Windows-Python `subprocess`
  (FileNotFoundError) — build request payloads with python (json.dumps to a
  cwd temp file), but run `railway` itself from bash. Git Bash `/tmp` ≠
  Windows-Python `/tmp`; use cwd-relative temp files and delete them.
- Passing `--variables '{...}'` inline mangles quotes. Write the JSON with
  `json.dump` to a file and pass `--variables "$(cat .tmp-vars.json)"`.
- Don't expand `$PORT` in double quotes when composing start commands —
  it must reach Railway literally.
- MSYS path-mangling eats single-letter flags: `reg query "HKCU\Environment" /v NAME`
  fails with "Invalid syntax" because Git Bash rewrites `/v` as a path.
  Prefix with `MSYS_NO_PATHCONV=1` (`MSYS_NO_PATHCONV=1 reg delete
  "HKCU\Environment" /v RAILWAY_TOKEN /f`) — or dump without `/v` and
  grep. When inspecting token env vars, filter output through
  `sed 's/rlwy_[a-zA-Z0-9_-]*/[REDACTED]/'` and never let the value
  reach the transcript.
- **Agent/tool shells must not rely on `~/.bashrc` for Railway auth**
  (hit live 2026-11-23): non-interactive tool shells don't source it,
  so `railway` inherits whatever stale `RAILWAY_TOKEN` /
  `RAILWAY_API_TOKEN` the parent process carries and authenticates
  with those — a valid `~/.railway-dev-token` reads as "Invalid
  RAILWAY_TOKEN" while the file is fine. In agent shells always pass
  the token explicitly and strip the account-key var:
  `env -u RAILWAY_API_TOKEN RAILWAY_TOKEN="$(cat ~/.railway-dev-token
  | tr -d ' \t\r\n')" railway <cmd>` (prod: same with the
  `.railway-prod-token` file). Sanity-check with
  `[ "$RAILWAY_TOKEN" = "$(cat ~/.railway-dev-token | tr -d ' \t\r\n')" ]` —
  env-vs-file equality, never by printing values.

## Networking gotchas

- Internal DNS names are not mechanical: `campus.audit` →
  `campusaudit.railway.internal` (punctuation stripped). Verify with the
  private-network status query, not by guessing.
- The mesh resolver is `fd12::10`, a bare IPv6 literal — nginx's `resolver`
  needs it bracketed. The stock nginx-image mechanism works: set service var
  `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1` and reference `${NGINX_LOCAL_RESOLVERS}`
  (already bracketed by the image's 15-local-resolvers.envsh).
- Do NOT curl a service's own public domain from inside Railway: internal
  DNS answers public names with mesh addresses where only the targetPort
  answers — connects on 443 hang (split-horizon hairpin trap).
- `privateIps` on a service's railway.internal endpoint can be empty while
  mesh egress works fine (observed 2026-10-30: ACTIVE + empty + fast
  responses) — it is NOT a reliable health signal. A genuinely broken mesh
  attachment shows up as behavior: fast `ECONNREFUSED` (nothing listening
  on the target) vs silent hangs (dead attachment/instance). The 2026-10-30
  gateway blackhole was fixed by INSTANCE REPLACEMENT (a plain redeploy) —
  not by any config change. Try a redeploy before filing tickets.
- nginx `proxy_pass` with a STATIC hostname resolves at config-load time
  (startup), before the mesh may be reachable — "host not found in
  upstream" crashes the container. For `*.railway.internal` targets use
  the variable form (`set $up "http://name:port"; proxy_pass $up;`) so the
  `resolver` directive handles per-request DNS.
- **`*.up.railway.app` resolves at Railway's edge even for names that were
  never created** (wildcard zone — a garbage subdomain returns an edge IP).
  DNS resolution is NOT proof a domain exists. Enumerate
  `domains.serviceDomains` / `domains.customDomains` via
  `railway status --json` (or GraphQL `serviceDomains`) to confirm what is
  actually attached. (This wildcard produced a false "public DB domain
  still exposed" finding on issue #958, 2026-11-03.)
- Deleting a service domain **cascade-deletes the derived
  `RAILWAY_SERVICE_*` reference variables** on other services and redeploys
  them. Those vars are string copies, nothing reads them from code — safe,
  but expect the redeploy wave.
- `railway variables -s <svc> -e <env> --kv` shows the MERGED view; a var
  visible there may not be deletable through that same scope if it lives in
  a shared/reference layer ("Variable not found"). Deleting the underlying
  domain is often the real removal path.

## Build and deploy-log gotchas

- A Dockerfile `COPY` of a file deleted from git keeps building ONLY while
  Railway's incremental snapshot still carries the old file; the first
  clean checkout fails deterministically (observed 2026-10-30: three
  gateway deploy failures). After deleting any file, grep the Dockerfile(s)
  for references to it.
- `railway logs -s <svc>` defaults to the latest SUCCESSFUL deployment's
  runtime logs — misleading when a deploy just failed. Get the failed
  deployment id (GraphQL `latestDeployment`) and run
  `railway logs <DEPLOYMENT_ID> -b` for build logs.
- Retry a failed build with
  `deploymentRedeploy(id:…, usePreviousImageTag:false){ id status }` —
  note it returns `Deployment!`, so it needs a selection set (unlike
  `serviceInstanceUpdate`, which returns bare Boolean).
- `gh pr update-branch N` puts a merge commit on the REMOTE branch only —
  `git push` from a stale local branch then needs
  `git pull --rebase origin <branch>` first.

## nginx gateway specifics (deploy/gateway/)

See `deploy/gateway/README.md`. Docker-entrypoint rules: the exec bit is
checked FIRST (`*.sh`/`*.envsh` without +x are ignored); executable `*.sh`
runs as a child process (exports lost), executable `*.envsh` is sourced
(exports propagate). Templates `/etc/nginx/templates/*.template` all render
to conf.d — the gateway build `rm`s stock templates before COPY. nginx `set`
directives re-assign silently: never leave duplicate upstream `set` lines in
a template (that was PR #1014's 502 bug).
