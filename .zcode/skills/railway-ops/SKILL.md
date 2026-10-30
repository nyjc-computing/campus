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

Project: `76e0b6d0-0832-41dc-841f-e3bc758d3eca`. Environments: `development`
(e954f5fa…, weekly autodeploys here), `staging` (43a0d8ed…), `production`
(bb2462d0…). `railway status --json` lists all three with
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

## Deploy queue and status checks

- Config-change deploys can sit `WAITING` ~4 min before `BUILDING`.
  Poll `activeDeployments[0]` per service (fields: `createdAt`, `status`,
  `meta.serviceManifest.deploy.startCommand`). Terminal: SUCCESS / CRASHED /
  SKIPPED / REMOVED. Expect ~5 min build+deploy for the Flask services.
- A failed healthcheck keeps the OLD deployment live (rollback-safe changes).
- `railway logs -s <svc> -e development --lines N` streams deploy logs
  (nginx access+error lines land here).

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
- `privateIps` on a service's railway.internal endpoint can be empty for
  recently API-created services; empty addresses correlate with broken mesh
  attachment (hanging outbound connects). Compare against a known-good
  service before trusting DNS results.

## nginx gateway specifics (deploy/gateway/)

See `deploy/gateway/README.md`. Docker-entrypoint rules: the exec bit is
checked FIRST (`*.sh`/`*.envsh` without +x are ignored); executable `*.sh`
runs as a child process (exports lost), executable `*.envsh` is sourced
(exports propagate). Templates `/etc/nginx/templates/*.template` all render
to conf.d — the gateway build `rm`s stock templates before COPY. nginx `set`
directives re-assign silently: never leave duplicate upstream `set` lines in
a template (that was PR #1014's 502 bug).
