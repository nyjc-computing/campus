# Circle Access Control

Circles are campus's access control mechanism: membership in circles
determines what a principal (user or circle) can and cannot access.
This document describes how circles are modelled, how the bootstrap
seeds them, and how requests will be authorized against them.

Status: the circle data model, membership API, and bootstrap are
shipped and live in `campus.api`. Request enforcement against circles
is designed but not yet implemented (see
[Enforcement](#enforcement-planned)).

## Placement: circles live in campus.api

Circles are domain data (school org structure) guarded by, and stored
alongside, the resources they protect. campus.api is also the
enforcement point — every domain consumer (classroom, timetable,
campus-cli) reaches campus data through it. Keeping circles here:

- lets enforcement read membership in-process, with no extra
  round-trip per request;
- keeps the dependency direction one-way (campus.api already
  authenticates every request against campus.auth; campus.auth never
  calls campus.api), avoiding a cycle if authorization data had to
  reference domain resources;
- leaves campus.auth as the identity service: authentication, tokens,
  and management authorization for auth resources (vaults, clients,
  users) via its access-grant store — a different question from
  "who may access domain resources".

The trade-off, accepted: campus has two permission systems
(campus.auth grants for auth management, circles for domain access),
and campus.api owns its own fail-closed gate discipline.

## Circle taxonomy

| Tag | Meaning | Seeded |
|-----|---------|--------|
| `root` | The single root of the circle hierarchy (the school domain). Has no parents. | `nyjc.edu.sg` |
| `admin` | Deployment-level admin sentinel. | `campus-admin` |
| `resource` | Guard for one API resource family. Hangs under the root. | one per guarded resource |
| `role` | A role on a resource: its members are the principals granted the role. Role circles never contain resources of their own. | `<resource>.admin` per resource circle |

Circle names are unique (best-effort, exact match), so role circles use
dotted names: the admin role on the timetable resource is
`timetable.admin`, a member of the `timetable` resource circle.

Bootstrap hierarchy after `CirclesResource.init_storage()`:

```
nyjc.edu.sg (root)
├── campus-admin (admin)
├── circles (resource)
│   └── circles.admin (role)      ← users with admin over /circles
├── timetable (resource)
│   └── timetable.admin (role)
├── assignments (resource)
│   └── assignments.admin (role)
├── bookings (resource)
│   └── bookings.admin (role)
└── submissions (resource)
    └── submissions.admin (role)
```

## Membership

A circle's `members` dict maps member IDs to integer access values.
Two kinds of member ID are accepted:

- **Circle members** (`uid-circle-...`, legacy `circle-...`): must
  exist in the circles collection. This is how the hierarchy is built
  (e.g. `timetable.admin` is a member of `timetable`).
- **User members** (email-shaped IDs; `UserID` is an `Email`):
  accepted without an existence check — the resource layer cannot
  validate user IDs against campus.auth. An unknown user ID is inert:
  enforcement matches caller IDs, so it fails closed.

Semantics that are convention, not contract, until decided:

- Access values are integers; `15` currently denotes full access
  (mirroring the seeded `campus-admin` → root edge).
- Membership matching is exact-match on the ID string.

Storage shape note: members are stored as a single `members` dict on
the circle record and updated by read-modify-write — never as
`members.{member_id}` update paths, because user emails contain dots
that the document backends would parse as nested-field separators.
This requires MongoDB ≥ 5.0 for literal dotted field names (the
in-memory test backend and PostgreSQL are unaffected). The
read-modify-write is best-effort under concurrency, like circle name
uniqueness.

## Bootstrap

`CirclesResource.init_storage()` is idempotent and seeds, in order:
the `@meta` bookkeeping record, the root circle, the `campus-admin`
sentinel, then a resource circle + `<resource>.admin` role circle for
each guarded resource (`circles`, `timetable`, `assignments`,
`bookings`, `submissions`), and finally adds the bootstrap admin user
to every role circle.

It runs at campus.api app start in every non-production environment
(same self-heal policy as the other api storage init). Production runs
schema management via migrations/scripts per
[prod-rollout.md](prod-rollout.md); the bootstrap must be run once
against production before enforcement ships.

**Temporary:** `ng_jun_siang@nyjc.edu.sg`
(`BOOTSTRAP_ADMIN_USER` in `campus/api/resources/circle.py`) is
seeded into every role circle until role administration has a
management flow. Removing it is a deliberate follow-up, not an
oversight.

## Managing circles

All circle administration is via the `/api/v1/circles/` endpoints
(contract documented in the route docstrings in
`campus/api/routes/circles.py` and summarised in
[campus-api-schema.md](campus-api-schema.md)). Mutations emit
`campus.circles.*` events via yapper.

Note that administration itself is **not yet gated**: any
authenticated principal can currently create circles or edit
membership. Gating circle administration behind `circles.admin` is
part of the enforcement work — and is urgent, since membership
editing is privilege escalation once enforcement lands.

## Enforcement (planned)

The intended model, at the campus.api route layer:

- A fail-closed gate helper resolves the caller's user ID (set by the
  authentication middleware on `flask.g`) and checks membership in the
  `<resource>.admin` role circle for the resource family the route
  serves. No membership → 403.
- Reads start ungated; mutations gate first. Circle administration
  routes gate behind `circles.admin`.
- Client principals (app tokens, no user) are denied domain-admin
  actions.
- Later: access-value tiers, transitive resolution through nested
  circles, and caching invalidated by the existing
  `campus.circles.*` yapper events.

The detailed design (gate placement, helper shape, principal rules)
is under discussion; this section is updated once decided.

## Open design questions

- Access-value semantics (what do the integer levels mean, and where
  are thresholds defined?)
- Role administration flow (who may edit role-circle membership, and
  via what UI/CLI) — replaces the hardcoded bootstrap admin.
- Transitive membership resolution (user → circle → role circle) and
  DAG/cycle policy.
- `move` (re-parenting) and `users` (enumerate users in a circle)
  endpoints are still 501 stubs.
- `sources` schema (external systems circles sync from) — tracked in
  #60.
