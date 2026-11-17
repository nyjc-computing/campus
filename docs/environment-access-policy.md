# Environment & Access Policy

Authoritative policy for how the Campus fleet's environments are used, who
may access what, and what may appear in logs. Ratified 2026-11-17. Every
deployment, troubleshooting, and developer document defers to this page —
where another document repeats one of these rules, this page is the source
of truth.

The three rules in short form:

1. **All testing in `development`. All code updates through `weekly`.**
   No code is pushed to or merged into `main` except through a PR from
   `weekly`.
2. **Production data is not accessed directly.** Railway access switches
   from personal `railway login` tokens to an environment-bound API key
   that only allows access to `development`. Production logs scrub
   sensitive secrets (Railway) and all PII plus sensitive secrets
   (campus.audit).
3. **Production Railway logs are superadmin-only.** Only the superadmin
   debugs deployment-side issues. Production audit logs are the one
   network debug surface available to students — via the campus-admin web
   UI or the campus API/CLI — so error messages must be clear enough to
   debug from, without revealing sensitive information.

## 1. Environments and branches

| Railway environment | Env id | Deploys from | Purpose |
|---|---|---|---|
| `development` | `e954f5fa…` | push to `weekly` (autodeploy) | all development and testing |
| `production` | `d5221f3b…` | push to `main` (autodeploy) | live service |
| `staging` | `43a0d8ed…` | — | legacy, unused; pending retirement |
| `production-legacy` | — | — | July-2025 fossil; pending retirement |

Branch model (the weekly → main cutover completed 2026-11-17):

```
task branch ──PR──> weekly ──────────PR (from weekly only)──> main
    │                  │                                        │
    └── (nothing auto-deploys)   push to weekly autodeploys     push to main
                                 development                    autodeploys production
```

- **All testing in `development`** (or locally). Never point test suites,
  smoke scripts, seed scripts, or one-off migrations at any other
  environment. The `staging` branch and Railway environment are retired
  conventions from the pre-cutover model and are unused.
- **All code updates through `weekly`.** Every change — code, docs, CI,
  config — lands on `weekly` via a PR from a task worktree branch
  ([CONTRIBUTING.md](CONTRIBUTING.md)).
- **`main` is release-only.** The only path to `main` is a PR whose head
  branch is `weekly` — no direct pushes, no PRs from feature branches.
  **Merging that PR is the production release action**: the push to
  `main` autodeploys the production fleet. The release runbook is
  [prod-rollout.md](prod-rollout.md) (§4/§6).

Enforcement today (GitHub ruleset `production` on `main`): PRs required,
one approving review, required status checks, no force-pushes, linear
history. What the ruleset cannot express — "PR head must be `weekly`",
"no admin bypass" — is convention plus review; open gaps are tracked in
the tracking issue referenced at the bottom of this page.

## 2. Railway access model

- **Routine Railway access is environment-bound to `development`.** A
  Railway API key scoped to the development environment replaces personal
  `railway login` tokens for day-to-day CLI/automation work. Personal
  tokens remain legitimate only for the superadmin's production duties.
- **Production is superadmin-only.** Only the superadmin touches
  production services on Railway — logs, variables, domains, SSH,
  redeploys — and only the superadmin debugs deployment-side issues.
- **Production data is never accessed directly.** No `railway ssh` into
  prod services, no tcp proxies to prod databases, no ad-hoc reads of
  prod Postgres/Mongo/bucket — including for debugging. Production data
  is reached only through the product's own surfaces (the versioned
  APIs, the campus-admin portal). The documented exceptions are the
  one-off bootstrap steps in the [prod rollout playbook](prod-rollout.md)
  (§3, standing up a new service); they are superadmin actions and are
  recorded when used.

> **Status (2026-11-17):** the Railway CLI is still on personal tokens
> from `railway login`; the API-key switch is the migration tracked in
> the issue referenced at the bottom of this page. Until it lands, apply
> the *access rules* above — who may touch what — as-is; the API key
> changes the *mechanism*, not the policy.

Practical recipes (CLI traps, GraphQL schema, deploy queueing) live in
the `railway-ops` skill (`.zcode/skills/railway-ops/SKILL.md`), which
also carries this access model.

## 3. Logs and scrubbing

- **Railway production logs** (deploy logs and runtime stdout) must not
  contain sensitive secrets: tokens, client secrets, API keys, database
  or vault URIs with embedded credentials. Services log configuration
  sparingly and never dump environment variables; when adding a log
  line, assume it will be read in a shared console.
- **campus.audit records in production** must scrub **all PII and
  sensitive secrets** — emails, names, tokens, secrets — because that
  trail is student-readable (§4). Redaction is producer-side
  (`redact_sensitive`, campus#805): when a new span/event field could
  carry PII or a secret, extend redaction where the record is *written*,
  not at read time. See [audit-tracing.md](audit-tracing.md).

## 4. Debug surfaces by role

| Role | Production debug surface | Explicitly not available |
|---|---|---|
| Superadmin | Railway prod logs and dashboard; everything below | — |
| Students / app authors | **Production audit trail**: campus-admin web UI audit views, campus API/CLI audit queries | Railway prod logs, prod databases, prod variables, SSH |
| Everyone | their own `development` environment and local tests | production anything |

- The production audit trail is the **only network debug surface
  available to students**. Apps that want debuggable production behavior
  must emit audit traces ([audit-tracing.md](audit-tracing.md); the
  student walkthrough's [§7](student-app-walkthrough.md#7-debugging-with-campusaudit)
  is the app-author recipe).
- **Error messages are a debug surface.** Since students debug from
  error messages plus audit traces, fleet-wide error messages should say
  clearly what failed and why (error code, which request/resource), and
  must not reveal sensitive information (secrets, tokens, internal
  hosts). When adding or changing an endpoint, ask: *with only this
  message and their audit traces, can a student tell what went wrong?*

## 5. Where this policy is encoded

- Branch workflow: [CONTRIBUTING.md](CONTRIBUTING.md), [PACKAGING.md](PACKAGING.md)
- Environments and services: [railway-architecture.md](railway-architecture.md)
- Production release runbook: [prod-rollout.md](prod-rollout.md)
- Railway CLI/API recipes and access notes: `.zcode/skills/railway-ops/SKILL.md`
- Quick reference: [AGENTS.md](../AGENTS.md)
- App-author view (§7): [student-app-walkthrough.md](student-app-walkthrough.md)

Known gaps between this policy and current reality are tracked in the
deviations sweep opened against it (see the issues linked from this
page's tracking issue, filed 2026-11-17).
