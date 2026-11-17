---
name: railway-ops
description: >-
  Traps and recipes for the Railway CLI/GraphQL API and Railway private
  networking in this project — service config mutations (schema changed),
  triggering redeploys, deleting services, deploy queueing, IPv6-only mesh
  requirements, and Windows shell quirks. Use when touching Railway services
  (vars, domains, healthchecks, start commands), debugging gateway/upstream
  failures, or waiting on deployments.
---

# Railway ops (campus project)

Project: `76e0b6d0-0832-41dc-841f-e3bc758d3eca`. Environments:
`development` (weekly autodeploys here) and `production` (`d5221f3b…`,
instances track `main` — the 2026-11-16/17 cutover). `staging` and the
fossil `production-legacy` were deleted 2026-11-17. `railway status
--json` lists the environments with
`environments.edges[].node.serviceInstances.edges[].node` carrying
`serviceName`, `serviceId`, `startCommand`, `activeDeployments`.

## Private networking is IPv6-only — listeners must bind `[::]`

- A container bound to `0.0.0.0` (IPv4 only) is **unreachable over the mesh**;
  the failure surfaces at the caller as `ECONNREFUSED` on
  `http://[fd12:…]:PORT` (fast RST) or a silent established-then-stall hang.
- Flask services (gunicorn) must use `--bind [::]:$PORT` (dual-stack on
  Linux; keeps public IPv4 working). Applied to dev auth/api/audit
  2026-10-30; **repeat on staging/production at rollout**.
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
- `serviceInstanceDeploy(environmentId:…, serviceId:…, latestCommit:true)` —
  explicitly triggers a deployment of the current config. **Config mutations
  do not always auto-trigger a deploy** (observed: of three identical
  startCommand updates, only one redeployed on its own; the other two needed
  this call).
- `serviceDomainDelete` also takes TOP-LEVEL args (no input wrapper); or use
  the CLI: `railway domain delete <DOMAIN_OR_ID> -s <svc> --yes`.
- `service delete` (CLI) is permission-refused in this workspace — delete
  services via the dashboard.

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
- Deploy-failure **notifications** remain dashboard-only: the API's
  `notificationRuleCreate` takes an undocumented
  `NotificationChannelConfig` scalar (blind-guessing its JSON shape is
  how you email nobody) — Project Settings → Notifications, rule
  scoped to the production environment.

## CLI shell traps (Windows / Git Bash)

- `railway` cannot be spawned from Windows-Python `subprocess`
  (FileNotFoundError) — build request payloads with python (json.dumps to a
  cwd temp file), but run `railway` itself from bash. Git Bash `/tmp` ≠
  Windows-Python `/tmp`; use cwd-relative temp files and delete them.
- Passing `--variables '{...}'` inline mangles quotes. Write the JSON with
  `json.dump` to a file and pass `--variables "$(cat .tmp-vars.json)"`.
- Don't expand `$PORT` in double quotes when composing start commands —
  it must reach Railway literally.

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
