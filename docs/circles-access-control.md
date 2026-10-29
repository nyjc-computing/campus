# Circle Access Control

Circles are campus's access control mechanism: membership in circles
determines what a principal can and cannot access. Circles contain
only other circles — users participate through their own **user
circle**, named after their email account, which also holds their
private resources. This document describes how circles are modelled,
how the bootstrap seeds them, and how requests are authorized
against them.

Status: the circle data model, membership API, the bootstrap, and
route enforcement are shipped and live in `campus.api` (enforcement:
[campus/api/authz.py](../campus/api/authz.py)). See
[Enforcement](#enforcement) for the mechanism, accepted 2026-10-30.

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
| `user` | A user's personal circle, named after their email account. Holds the user's private resources and represents the user in role memberships. | the bootstrap admin's (temporary) |

Circle names are unique (best-effort, exact match), so role circles use
dotted names: the admin role on the timetable resource is
`timetable.admin`, a member of the `timetable` resource circle. User
circles are named after the email account, which is itself unique and
stable (`UserID` is an `Email`), so a user's circle is addressable by
their email address.

Bootstrap hierarchy after `CirclesResource.init_storage()`:

```
nyjc.edu.sg (root)
├── campus-admin (admin)
├── ng_jun_siang@nyjc.edu.sg (user, standalone — private resources)
├── circles (resource)
│   └── circles.admin (role)      ← user circles granted admin over /circles
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

A circle's `members` dict maps member identifiers to integer access
values. **Circles contain only circles**: a member identifier is
either

- a **circle UID** (`uid-circle-...`, legacy `circle-...`), which must
  exist in the circles collection — this is how the hierarchy is
  built (e.g. `timetable.admin` is a member of `timetable`); or
- a **user circle's email name** — adding a user to a circle means
  adding their user circle, and the user circle record must exist
  (a missing user circle is a 409, not an inert entry).

Members are stored under the identifier they were added with. The
email name needs no UID resolution: it is unique, stable, and is what
enforcement resolves a caller to anyway (the caller's email → their
user circle's membership entries).

Semantics that are convention, not contract, until decided:

- Access values are integers; `15` currently denotes full access
  (mirroring the seeded `campus-admin` → root edge).
- Membership matching is exact-match on the identifier string.

Storage shape note: members are stored as a single `members` dict on
the circle record and updated by read-modify-write — never as
`members.{member_id}` update paths, because user-circle email names
contain dots that the document backends would parse as nested-field
separators. This requires MongoDB ≥ 5.0 for literal dotted field
names (the in-memory test backend and PostgreSQL are unaffected). The
read-modify-write is best-effort under concurrency, like circle name
uniqueness.

## Bootstrap

`CirclesResource.init_storage()` is idempotent and seeds, in order:
the `@meta` bookkeeping record, the root circle, the `campus-admin`
sentinel, the bootstrap admin's user circle, then a resource circle +
`<resource>.admin` role circle for each guarded resource (`circles`,
`timetable`, `assignments`, `bookings`, `submissions`), and finally
adds the bootstrap admin's user circle to every role circle.

It runs at campus.api app start in every non-production environment
(same self-heal policy as the other api storage init). Production runs
schema management via migrations/scripts per
[prod-rollout.md](prod-rollout.md); the bootstrap must be run once
against production before enforcement ships.

**Temporary:** `ng_jun_siang@nyjc.edu.sg`
(`BOOTSTRAP_ADMIN_USER` in `campus/api/resources/circle.py`) gets a
user circle seeded and added to every role circle until role
administration and user-circle provisioning have management flows.
Removing it is a deliberate follow-up, not an oversight.

## Managing circles

All circle administration is via the `/api/v1/circles/` endpoints
(contract documented in the route docstrings in
`campus/api/routes/circles.py` and summarised in
[campus-api-schema.md](campus-api-schema.md)). Mutations emit
`campus.circles.*` events via yapper.

Administration is gated: every mutating circles endpoint requires
membership in the `circles.admin` role circle (see below). Membership
editing is privilege escalation once circles gate access, which is
why the circles family gates first.

## Enforcement

Implemented 2026-10-30 (mechanism accepted by the maintainer; labels
optional). `campus/api/authz.py` provides the fail-closed gate:

```python
authz.require_resource_admin(resource, action_label=None)
```

- **Decision**: the caller must be a user principal (bearer token)
  whose user ID — the email, which is also their user circle's name —
  appears in the `<resource>.admin` role circle's members dict. The
  role circle is resolved by name; a missing role circle denies
  (fail-closed, no 500). User circles are named after the email, so
  this is a direct members-dict lookup: no resolution hop.
- **Denials (403)**: client principals (HTTP Basic or app-scoped
  tokens — domain administration must be attributable to a user, the
  #854 rule), authenticated users without the role, and any caller
  when the role circle does not exist. `action_label` is an optional
  verb phrase shaping the denial message only; labels never gate.
- **Placement**: gate calls live in the route modules, before any
  resource work; the resources stay ungated for in-process callers
  (the same discipline as campus.auth's authz).
- **Coverage**: mutation routes of all five guarded families
  (circles, timetable, assignments, bookings, submissions) gate;
  circle administration gates behind `circles.admin` first, since
  membership editing is privilege escalation. Reads are open for now.
  emailotp is user-facing OTP with no circle and stays ungated.
- **Tests**: unit coverage in `tests/unit/api/test_authz.py`; the
  contract suites grant their test user role membership via
  `tests.fixtures.circles.grant_circle_admin`, and negative 403 cases
  live in `tests/contract/api/test_api_circles.py`.

Later refinements, in rough order: access-value tiers (the gate takes
a level checked against the member's access value), transitive
resolution through nested circles, caching invalidated by the
existing `campus.circles.*` yapper events, and private-resource
access resolving through the owning user's circle contents.

## Open design questions

- Access-value semantics (what do the integer levels mean, and where
  are thresholds defined?)
- User-circle provisioning for users other than the bootstrap admin
  (created lazily on first campus.api request? via an admin flow?
  synced from campus.auth accounts?)
- How resources attach to circles (`sources` schema, #60) — user
  circles' private resources and role circles' no-resources rule.
- Role administration flow (who may edit role-circle membership, and
  via what UI/CLI) — replaces the hardcoded bootstrap admin.
- Transitive membership resolution (circle → circle → role circle)
  and DAG/cycle policy.
- `move` (re-parenting) and `users` (enumerate users in a circle)
  endpoints are still 501 stubs.
