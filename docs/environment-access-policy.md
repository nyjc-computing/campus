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
   debugs deployment-side issues. The production audit trail is
   superadmin/admin-only; students may access audit traces on the
   **development environment only**. Error messages are therefore
   students' production debug surface — keep them clear, never
   revealing sensitive information.

## 1. Environments and branches

| Railway environment | Env id | Deploys from | Purpose |
|---|---|---|---|
| `development` | `e954f5fa…` | push to `weekly` (autodeploy) | all development and testing |
| `production` | `d5221f3b…` | push to `main` (autodeploy) | live service |

The `staging` (`43a0d8ed`) and `production-legacy` Railway environments
were **deleted 2026-11-17** — two environments only. The retired
`staging` git branch and its ruleset were deleted the same day
([#1122](https://github.com/nyjc-computing/campus/issues/1122)).

Branch model (the weekly → main cutover completed 2026-11-17):

```
task branch ──PR──> weekly ──────────PR (from weekly only)──> main
    │                  │                                        │
    └── (nothing auto-deploys)   push to weekly autodeploys     push to main
                                 development                    autodeploys production
```

- **All testing in `development`** (or locally). Never point test suites,
  smoke scripts, seed scripts, or one-off migrations at any other
  environment. `staging` is fully retired (branch, ruleset, and Railway
  environment all deleted 2026-11-17, #1122).
- **All code updates through `weekly`.** Every change — code, docs, CI,
  config — lands on `weekly` via a PR from a task worktree branch
  ([CONTRIBUTING.md](CONTRIBUTING.md)).
- **`main` is release-only.** The only path to `main` is a PR whose head
  branch is `weekly` — no direct pushes, no PRs from feature branches.
  **Merging that PR is the production release action**: the push to
  `main` autodeploys the production fleet. The release runbook is
  [prod-rollout.md](prod-rollout.md) (§4/§6).

Enforcement (GitHub ruleset `production` on `main`): PRs required, one
approving review, required status checks, no force-pushes, linear
history. GitHub rulesets cannot restrict a PR's head branch (conditions
only select the target branch), so "PRs from `weekly` only" is
machine-enforced by the required `head-branch-is-weekly` CI guard
(`.github/workflows/main-pr-head-guard.yml`, added with this policy).
**Admin bypass stays enabled by design** — the documented emergency
path. Dependabot is pinned to `weekly` via `target-branch`. Residual
gaps are tracked in
[#1131](https://github.com/nyjc-computing/campus/issues/1131)
([#1121](https://github.com/nyjc-computing/campus/issues/1121) for the
ruleset itself).

**Ruling 2026-11-17 (access model):** campus-admin portal access will be
relaxed to any account holding one or more access grants
([#1129](https://github.com/nyjc-computing/campus/issues/1129),
implementation tracked on campus-admin); student accounts may access
audit traces on the **development environment only** — the production
audit trail remains superadmin/admin-only.

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
  (§3) and the [migration runbook](migration-protocol.md#staging--production-style-environments-manual-runbook)
  — superadmin actions, each recorded when used.

> **Status (2026-11-17):** the Railway CLI is still on personal tokens
> from `railway login`; the API-key switch is tracked as
> [#1123](https://github.com/nyjc-computing/campus/issues/1123). Until it
> lands, apply the *access rules* above — who may touch what — as-is; the
> API key changes the *mechanism*, not the policy.

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
  sensitive secrets** — names, tokens, secrets — because audit records
  are readable by the superadmin/admins. Ruling 2026-11-17:
  college-issued identity identifiers — `user_id` values and other
  `*.nyjc.edu.sg` addresses — are **not** PII (institutional IDs, not
  personal emails), so identity attribution may keep using them;
  personal (non-college) email addresses, personal names, tokens, and
  secrets stay in scrub scope. Redaction is producer-side
  (`redact_sensitive`, campus#805): when a new span/event field could
  carry PII or a secret, extend redaction where the record is *written*,
  not at read time. See [audit-tracing.md](audit-tracing.md).

## 4. Debug surfaces by role

| Role | Debug surface | Explicitly not available |
|---|---|---|
| Superadmin | Railway prod logs and dashboard; the production audit trail; everything below | — |
| Admins (grant-holders) | campus-admin portal (gate relaxed per the §1 ruling, implementation on campus-admin); production audit views per `AUDIT_ADMINS` | Railway prod logs, prod databases |
| Students / app authors | **Audit traces on `development` only** (portal audit views or campus API/CLI); error messages everywhere | production audit trail, Railway prod logs, prod databases, prod variables, SSH |
| Everyone | their own `development` environment and local tests | production anything |

- **Audit tracing is the debug surface students get on `development`**
  (§1 ruling): enable it on your app
  ([audit-tracing.md](audit-tracing.md); the student walkthrough's
  [§7](student-app-walkthrough.md#7-debugging-with-campusaudit) is the
  app-author recipe). The production trail is reserved for the
  superadmin/admins — production questions from students go through
  clear error messages and a superadmin, not self-service log access.
- **Error messages are a debug surface.** Students debug from error
  messages plus their dev-environment audit traces, so fleet-wide error
  messages should say clearly what failed and why (error code, which
  request/resource), and must not reveal sensitive information (secrets,
  tokens, internal hosts). When adding or changing an endpoint, ask:
  *with only this message and their dev audit traces, can a student tell
  what went wrong?*

## 5. Where this policy is encoded

- Branch workflow: [CONTRIBUTING.md](CONTRIBUTING.md), [PACKAGING.md](PACKAGING.md)
- Environments and services: [railway-architecture.md](railway-architecture.md)
- Production release runbook: [prod-rollout.md](prod-rollout.md)
- Railway CLI/API recipes and access notes: `.zcode/skills/railway-ops/SKILL.md`
- Quick reference: [AGENTS.md](../AGENTS.md)
- App-author view (§7): [student-app-walkthrough.md](student-app-walkthrough.md)

Known gaps between this policy and current reality were swept on
2026-11-17 and are tracked on the sweep tracker
[#1131](https://github.com/nyjc-computing/campus/issues/1131) — among
them: main-ruleset admin bypass (#1121), staging retirement (#1122), the
Railway API-key migration (#1123), the audit-event redaction gap
(#1124), the PII ruling (#1125 — resolved: nyjc.edu.sg identifiers are
not PII), secrets at WARNING in Railway logs
(#1126), OAuth-proxy error dumps (#1127), error-message leakage
(#1128 + campus-common#8 + campus-core#8), the AUDIT_ADMINS portal-gate
ruling (#1129 — resolved: portal relaxes to grant-holders, students
audit on development only), gateway access-log query strings (#1130), and the
flask-campus redaction extensions
([flask-campus#20](https://github.com/nyjc-computing/flask-campus/issues/20)).
