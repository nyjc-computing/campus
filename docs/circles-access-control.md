# Circle Access Control

Circles are campus's access control mechanism: membership in circles
determines what a principal can and cannot access. Circles contain
only other circles — users participate through their own **user
circle**, named after their email account, which also holds their
private resources. This document describes the ratified access model
(ratified 2026-11-23, campus#1216), how the bootstrap seeds it, and
how requests are authorized against it.

Status: this document **supersedes** every earlier description of the
campus.api authorization model, including the pre-ratification
membership/value conventions (the "15 = full access" era) and the
`<resource>.admin` role-circle structure. Enforcement is live in
[campus/api/authz.py](../campus/api/authz.py); see
[Enforcement](#enforcement).

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

The boundary is ratified (operator, 2026-11-06): campus.api resource
routes never consult the access-grant store, and grant vocabularies
opened for domain resources (e.g. `timetable:read/write/admin`,
campus#1068) confer no campus.api authority.

## The model

### Grant circles and member-list circles

Circle families split by role:

- **Grant circles** (tag `resource`) — one per guarded resource
  family (`timetable`, `subjcombi`, `venues`, `files`, ...). These
  are the circles authorization resolves against: authority on the
  family is the access value carried by an edge into the grant
  circle. Grant circles hang under the root circle.
- **Member-list circles** — organizational circles that hold people:
  primary groups (`staff`, `student`), committee circles
  (`committees.timetabling`), venue-category circles
  (`venues.sports-facilities`), and user circles. A member-list
  circle confers authority only through the values on the edges that
  connect it (or its ancestors) to grant circles.

Committee circles are generally contained in the grant circles they
administer (one membership carries all members, present and future);
a family administered by a single person may hold that person's user
circle directly.

### The `campus` wildcard

`campus` is a reserved circle seeded at init. A `campus:admin`
membership confers **admin on every resource family** — the one
cross-family authority in the model, checked by the authz layer
before any family resolution. Seeded member: the platform admin
(`campus-admin@nyjc.edu.sg` in production). `campus` is a reserved
label and can never be reused as a circle name.

## Access values

Every membership edge that resolves to a grant circle carries an
integer access value. A value encodes **two independent permission
sets**: group-scope (`G` — authority over the family's shared
resources) and self-scope (`S` — authority over the caller's own
resources within the family). Layout (8 bits, left-padded):

```
bit:   7    6    5    4    3    2    1    0
      [0] [G-c][G-m][G-r][S-c][S-m][S-r][reserved=0]
```

`c⇒m⇒r` holds within each field (create implies modify implies
read). Group authority mirrors into self: whoever holds a group-scope
role holds at least the same powers over their own resources.

Exactly five constants are valid; edge values MUST be one of them
(API validates against the set; the CLI accepts names and numeric
equivalents). Arbitrary integers are rejected at write time.

| name | bits | value | meaning |
|------|------|-------|---------|
| `admin` | `0_111_111_0` | **126** | create/modify/delete/read — group and own |
| `editor` | `0_011_011_0` | **54** | modify+read — group and own (no create/delete) |
| `viewer` | `0_001_001_0` | **18** | read — group and own |
| `self` | `0_000_111_0` | **14** | own resources only: create/modify/delete/read |
| `guest` | `0_000_001_0` | **2** | own resources only: read |

The set is ordered (`guest < self < viewer < editor < admin`) and
closed under max — a principal's effective value per scope is the
maximum across their resolving paths, so multiple memberships
compose by taking the strongest grant per scope.

The pre-ratification 4-bit values (15/11/9/7/1) are retired; the
migration rewrites edges to constants, and the validator rejects
non-constants, so legacy values cannot re-enter.

## Baseline: primary-group membership confers defaults

Every account's personal circle is a member of exactly one **primary
group**, and that membership's access value is the account's
**platform-wide floor**:

- `staff:viewer` — every staff member reads everything school-wide by
  default (timetables, venues, bookings browse — matching v1's
  staff-wide browse).
- `student:guest` — every student reads own-scope resources only
  (own timetable via subject-match, own mapping, own files).
  Students hold no venues access: in v1 both booking and
  booking-browse were staff-only.

Ratified 2026-11-23: staff baseline `viewer` deliberately includes
reading all `subjcombi` mappings.

Membership values on edges that do not resolve to a grant circle
(user→group containment, group→group organizational containment) are
not consulted for authority; only the primary-group baseline and
family-directed edges confer access.

## Resolution

For principal *u*, family *F*, operation *op*:

1. **Wildcard**: if *u* resolves transitively to `campus` at
   `admin`, allow.
2. **Scope class**: the family's operation table (below) classifies
   *op* as group-scope (`G`) or self-scope (`S`), and states what
   "own" denotes.
3. **Self-scope ops**: effective value = max of the `S` fields
   across *u*'s baseline and every family-directed edge applicable to
   *u*. Never narrowed away by a category subcircle — a
   science-labs viewer who is staff can still create their own
   bookings through their own-scope edges.
4. **Group-scope ops**: if *F* declares a category dimension (today:
   `venues`, via the venue's `metadata.category` slug) and *u* holds
   the matching category subcircle (`venues.<slug>`), that subcircle's
   edge value is authoritative — narrowest wins. Otherwise the
   effective value is the max across all family-directed edges and
   the baseline.
5. **Check**: the op's required permission bit must be set in the
   effective value. Fail-closed everywhere: missing grant circle,
   missing baseline, unresolvable membership, or client principals
   all deny.

### Family × operation table

| family | group-scope operations | self-scope ("own") | notes |
|---|---|---|---|
| `timetable` | version CRUD, pointer moves, attachments | read own timetable (subject-match) | no own-write semantics |
| `subjcombi` | set/cancel mappings | read own mapping | mutations are committee-only |
| `venues` | venue CRUD; booking decisions (approve/deny) on the family's venues | create/modify/withdraw **own bookings** | venue CRUD needs `G-c`; deciding needs `G-m` |
| `users` | directory read: list/search the user base — `G-r` only, the family honors **no write semantics** (identity mutation stays in campus.auth's walled management surface, #1226) | read **own** record (`S-r`; every baseline constant carries it) | served by the read-only `/users` facade: staff get the full list via the `staff:viewer` baseline; a caller without group-read is scoped by query rewrite to the members of circles they can read (guest memberships confer nothing) |
| `files` | file management | own uploads | full `self` honored |
| `assignments`, `submissions`, `circles`, `hostedapps` | family CRUD | inapplicable — `S` fields ignored | `G`-only |

Where "own" is inapplicable, self-scope grants are vacuous; a family
whose table has no self-scope rows rejects `S`-only values on its
edges at write time (`guest`/`self` target families that define own
semantics).

### Venue booking authority (example walk-through)

A PE teacher holds `staff:viewer` (baseline) plus membership in
`venues.sports-facilities`, whose edge into `venues` carries
`admin`:

- approving a sports-facilities booking: group-scope op; the
  matching category subcircle's `G` field (`admin`) is authoritative
  → allowed;
- approving a physics-lab booking: no `science-labs` membership;
  falls to family-level edges — baseline `viewer` has no `G-m`
  → denied;
- editing their own sports-facilities booking: self-scope op; max of
  `S` fields (baseline `viewer`'s `S-r`, the subcircle edge's
  `S-cmr`) → allowed, never narrowed away.

## Notation and grammar

- **Membership notation**: `<absolute-path>:<constant>`, e.g.
  `venues.sports-facilities:admin`. An absolute path is the
  containment chain from the first ancestor below the root; the root
  circle (`nyjc.edu.sg`) never appears in a path (its dots would
  break the grammar — quoted path components are disallowed; the
  escape hatch may be revisited only if genuinely needed). A circle
  with multiple parents has one absolute path per parent chain.
- **Labels**: `[a-z0-9-]+`, no leading/trailing/consecutive hyphens,
  length-capped; venue categories slug via lowercase + collapse
  non-alphanumeric runs to hyphens ("Sports Facilities" →
  `sports-facilities`). The reserved labels — the five constant
  names (`admin`, `editor`, `viewer`, `self`, `guest`) plus `campus`
  — are rejected as exact circle names, which permanently prevents a
  `venues.admin`-style subcircle. Substring overlaps
  (`self-viewer`) are a documentation concern, not a parse one.
- **User circles** are named after emails; they are leaves, never
  addressed in paths, and exempt from the label charset.
- **Uniqueness** is per-parent: two families may each contain a
  `sports-facilities` subcircle. (The historical global best-effort
  name uniqueness relaxes accordingly.)
- **Paths are derived from containment**, not stable identifiers:
  re-parenting changes addresses. The category→subcircle resolution
  matches label-within-family, never a path string. The `move`
  endpoint (still a stub) must preserve this invariant.

## Membership

A circle's `members` dict maps member identifiers to access values.
**Circles contain only circles**: a member identifier is either

- a **circle UID** (`uid-circle-...`), which must exist in the
  circles collection — this is how the hierarchy is built; or
- a **user circle's email name** — adding a user to a circle means
  adding their user circle, and the user circle record must exist
  (a missing user circle is a 409, not an inert entry).

Members are stored under the identifier they were added with. The
email name needs no UID resolution: it is unique, stable, and is what
enforcement resolves a caller to anyway.

Single-membership probe: `GET /api/v1/circles/{circle_id}/members/{member_id}`
returns the member's access value, or 404 when unreachable (the
expected negative answer, not an error; a missing circle is a 409).
Resolution mode: by default the probe resolves through member group
circles — the enforcement gate's own semantics; the two answer
through the shared resolver (`resources.circle.resolve_member`),
so their decisions agree by construction (a randomized unit test
pins gate == probe). `?resolve=direct` is the explicit direct-only
spelling. The walk is cycle-safe via a visited set and skips stale
member keys (circle deleted after being added) fail-closed without
blocking resolution through the remaining members.

Inverted check: `GET /api/v1/users/{user_id}/roles` enumerates the
user's memberships as absolute paths with their access values —
sorted by path, each entry carrying `circle_id`, `path`,
`access_value`, `direct`, `via`. A user with no resolvable
memberships answers an empty list. Ungated like the other circles
reads.

Enumeration: `GET /api/v1/circles/{circle_id}/users` lists the user
circles reachable through a circle's membership graph (transitive),
answering the audit question "who is `venues:admin`" without
hand-walking members dicts.

## Bootstrap

`CirclesResource.init_storage()` is idempotent and seeds, in order:
the `@meta` bookkeeping record, the root circle, the reserved
`campus` wildcard circle, the bootstrap admins' user circles, and a
grant circle per guarded resource family. It does **not** seed role
circles (abolished) and does not create primary groups or
memberships — those belong to provisioning flows.

- **Grant circles seeded**: `circles`, `timetable`, `assignments`,
  `submissions`, `subjcombi`, `venues`, `files`, `hostedapps` —
  each contained in the root. ("bookings" is deliberately absent:
  booking authority is venue-derived.)
- **`campus` wildcard**: seeded under the root with the platform
  admin's user circle as its member at `admin`. In dev, the dev
  admin identities join `campus` instead of per-family grants.
- **Baseline groups** (`staff`, `student`) are provisioning
  artifacts, not bootstrap: a provisioning flow creates the group,
  adds user circles at the baseline constant (`staff:viewer`,
  `student:guest`), and contains the group in the families its
  baseline should reach beyond reads (e.g. `staff` → `venues` at
  `self` for own-bookings management).

It runs at campus.api app start in every non-production environment
(same self-heal policy as the other api storage init). Production
runs schema management via migrations/scripts per
[prod-rollout.md](prod-rollout.md); the bootstrap must be run once
against production before enforcement ships.

**Temporary:** the accounts in `BOOTSTRAP_ADMIN_USERS`
(`campus/api/resources/circle.py`) get user circles seeded at init
until user-circle provisioning has a management flow. Their
authority is whatever edges reference them — the bootstrap adds the
dev/platform admins to `campus` (and, in dev only, keeps test
accounts workable via provisioning). Removing or extending the list
is a deliberate follow-up, not an oversight.

**Migration note (from the role-circle model):** environments seeded
before ratification still hold `<resource>.admin` role circles and
4-bit edge values. The rollout order is: create the new circles and
edges first (additive — the legacy gates keep working while legacy
circles exist), refactor and ship the value-based gates, verify, then
delete the role circles and rewrite legacy edge values to constants.
Until the rewrite lands, edges carrying non-constant values resolve
no group-scope authority — add the new edges before shipping the new
gates.

## Managing circles

All circle administration is via the `/api/v1/circles/` endpoints
(contract documented in the route docstrings in
`campus/api/routes/circles.py` and summarised in
[campus-api-schema.md](campus-api-schema.md)). Mutations emit
`campus.circles.*` events via yapper.

Administration is gated: every mutating circles endpoint requires
effective `admin` on the `circles` family (wildcard or family edge —
membership editing is privilege escalation once circles gate access,
which is why the circles family gates first).

## Enforcement

`campus/api/authz.py` provides the fail-closed gates:

```python
authz.require_resource_access(
    resource, scope, permission, action_label=None, category=None
)
authz.require_resource_admin(resource, action_label=None)   # G-create shorthand
authz.require_user_principal(action_label=None)             # attribution without a role
```

- **Decision**: `require_resource_access` implements the Resolution
  section — wildcard, scope class per the family table, baseline and
  family-directed edges, category narrowing for `venues` booking
  ops. `require_resource_admin(resource)` is the common
  group-scope-create gate (venue/timetable/... CRUD) expressed
  through the same resolver. All gates resolve the caller to their
  user circle's email name; the shared resolver is the same
  implementation the membership probe answers through, so gate and
  probe cannot drift.
- **Denials (403)**: client principals (HTTP Basic or app-scoped
  tokens — domain administration must be attributable to a user, the
  #854 rule), authenticated users whose effective value lacks the
  required bit, and any caller when the grant circle does not exist.
  `action_label` is an optional verb phrase shaping the denial
  message only; labels never gate.
- **Placement**: gate calls live in the route modules, before any
  resource work; the resources stay ungated for in-process callers
  (the same discipline as campus.auth's authz).
- **Coverage**: mutation routes of all guarded families gate; the
  `circles` family gates first, since membership editing is
  privilege escalation. Reads gate per the family tables: baseline
  `viewer`/`guest` make ordinary reads available to every staff and
  student principal respectively, so read gates deny only callers
  with no baseline and no applicable edge (bare client principals
  are never denied on reads they could perform as attribution-less
  consumers — files/hostedapps keep their ratified write-open
  posture until per-namespace gates land).
- The randomized gate == probe pin test covers value semantics and
  category narrowing.

## Open design questions

- User-circle provisioning for users other than the bootstrap admin
  (created lazily on first campus.api request? via an admin flow?
  synced from campus.auth accounts?).
- `move` (re-parenting) endpoint is still a 501 stub; its contract
  must keep paths-derived-from-containment honest.
- Role administration flow (who may edit family edges, and via what
  UI/CLI) — currently the platform admin via `campus` + CLI.
