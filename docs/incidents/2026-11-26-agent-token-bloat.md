# Incident 2026-11-26 — agent token bloat during the gateway downstream rollout

**Scope:** agent-process cost, not a production fault. The multi-repo
gateway rollout (flask-campus fc#47/#50, the per-app opt-ins, prod
promotion) completed successfully; this document records why it cost
disproportionately many agent tokens and what changes for future
sessions. Advice locations (the railway-ops skill, agent memory) carry
**pointers to this file, not copies** — this file is the documentation.

## What the rollout was

Campus-gateway downstream-app epic (campus#1295, #1274): routing five
consumer apps, per-app opt-ins, prod promotion for the timetable slice,
then the fc#50 centralization (PrefixFix) replacing three scoped
patches. Roughly a dozen merged PRs across five repos plus operator
Railway work (variables, registry edits, deploys).

## Causes, by token cost

### 1. Per-session fleet re-derivation (largest)

Every session re-derived service IDs, mesh names, public domains,
tracked branches, and deployment state through multi-step GraphQL
probing — including several failed query shapes
(`serviceInstances` plural doesn't exist; `ServiceSource` has no
branch; `ServiceInstanceUpdateInput` introspection is opaque) before
landing on a working pattern. Mesh names also needed a lookup each
time to avoid the documented guessing trap.

**Mitigation:** bounded re-derivation stays necessary — a committed
fleet snapshot (stable service IDs / architecture table) was considered
and **deliberately rejected**: service IDs and the deployment
architecture are not stable yet (services still being added, renamed,
and re-architected), so a snapshot would rot silently and mislead.
Re-derive per session, with targeted queries only. Revisit the
snapshot idea when the fleet shape stabilizes.

### 2. Patch-then-generalize arc (largest structural cost)

The mount story shipped as three scoped patches — `login_prefix`
(fc#47), per-app `static_url_path` mounts, gateway-side static
rewrites (#1306, later reverted) — before the general fix
(fc#50 PrefixFix) replaced all of them. Each narrow patch cost a full
ship-verify cycle that was then reverted or superseded.

**Mitigation:** when the same symptom recurs across fixes
(unroutable root-absolute URLs), raise the "what is the general
mechanism?" question *before* shipping the next narrow patch. Narrow
fixes remain right when a decision is genuinely pending — make that a
conscious choice, not a default.

### 3. Ad-hoc script composition

The same tooling was written from scratch per use: the deploy
poller (`railway status --json` + per-service GraphQL, wrapped in
inline python) ran dozens of times; the OAuth redirect_uri setter was
composed twice (dev, prod); deploy-verification curl matrices were
re-typed per app.

**Mitigation:** the proven versions are now permanent —
`scripts/railway_wait_deploy.py` (poll a service set to SUCCESS after a
timestamp) and `scripts/railway_set_redirect_uris.py` (operator-
principal redirect_uri setter with exact-set verification). Use them;
extend them rather than re-composing.

### 4. Shell and write-path fights

- **Heredocs**: a multi-file heredoc composition truncated mid-stream
  (issue bodies written short, discovered only on readback); a heredoc
  + inline-python mix hit the Git-Bash `/tmp` vs Windows-Python `/tmp`
  mismatch; a `gh release create` after a heredoc failed on zsh glob
  expansion of asset paths.
- **Inline python-in-bash**: multi-line `python -c` inside compound
  commands broke on quoting repeatedly (blocked tool calls).
- **GraphQL create flake**: `gh pr create` intermittently 500s
  (GraphQL); the REST path (`gh api repos/:o/:r/pulls -X POST`,
  `-F body=@file`) worked every time.
- **docker run without `-d`**: a foreground nginx blocked a whole tool
  call until killed.
- **MSYS path mangling**: `-w "%{http_code} /path -> %{redirect_url}"`
  format strings had `/path` rewritten to `C:/Program Files/Git/path`.

**Mitigation (the heredoc rule and friends):**

- **Avoid heredocs in agent shells.** Anything longer than ~10 lines
  or destined for a tool (`-F body=@file`, `--variables @file`): use
  the Write tool to create the file, then pass it by path. If a heredoc
  is truly unavoidable, keep it short and verify the file (`wc -l`,
  `tail`) before using it.
- GitHub writes: `gh api` REST endpoints (`-X POST`/`-X PATCH`) instead
  of the GraphQL `gh pr create` path; bodies by file reference.
- Temp/script files via the Write tool into a dedicated directory
  (`.registry/` was used this rollout); never `/tmp` for anything
  Windows-Python will read.
- Long-running containers: `-d` always; verify with `exec`, not an
  attached run.

### 5. Full-file reads

Large docs (`railway-variables.md`, `login_manager.py`, fleet dumps)
were read wholesale where a targeted grep answered the question.

**Mitigation:** grep-first recon with bounded context (the existing
"token-efficient verification method" note) — applied late in this
rollout; keep it applied from the start.

## What came out of the incident

- `scripts/railway_wait_deploy.py` — poll a service set to SUCCESS.
- `scripts/railway_set_redirect_uris.py` — operator-principal
  redirect_uri setter.
- Index pointers from the railway-ops skill and agent memory (this
  file is the documentation; those are indexes).
- The related `weekly`-branch deletion (promotion PR merged with
  `--delete-branch`) is documented separately in
  [prod-rollout.md §6](../prod-rollout.md) — same rollout, different
  incident class (merge policy, not token cost).
