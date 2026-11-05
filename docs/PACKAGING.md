# Campus Packaging Guide

## Overview

Campus ships as a **fleet of six distributions** under one flat `campus` import namespace (PEP 420). Each shared layer lives in its own repository, is released as a version-pinned wheel, and is consumed only by whoever actually imports it — downstream apps never install a campus *service* or a database driver.

| Distribution | Contents | Consumed by |
|---|---|---|
| [campus-common](https://github.com/nyjc-computing/campus-common) | `campus.common` — env, errors, schema, protocol constants, service URL registry, utils, validation | everything |
| [campus-model](https://github.com/nyjc-computing/campus-model) | `campus.model` — entity dataclasses + header value classes | suite, SDK, profile, classroom |
| [flask-campus](https://github.com/nyjc-computing/flask-campus) | `campus.flask_campus` glue + `campus.audit.{middleware,client,http,roles}` | the four Flask apps + suite |
| [campus-deploy](https://github.com/nyjc-computing/campus-deploy) | `campus.deploy` — create_app, health/landing/OpenAPI conventions | suite, nyxchange |
| [campus-core](https://github.com/nyjc-computing/campus-core) | `campus.storage` + `campus.webauth` + `campus.services` (DB drivers as extras) | campus-suite **only** |
| [campus-suite](https://github.com/nyjc-computing/campus) (this repo) | `campus.auth`, `campus.api`, `campus.audit` services + `campus.yapper` | deploy targets only — **no app installs it** |

**Key Benefits:**
- Independent release cadence per layer (strict-0.x: patch = additive, minor = breaking)
- "Apps must not touch storage/webauth" is physically true — they cannot install it
- No app drags a database driver; drivers are campus-core extras
- Each dist's boundary guard + interface manifest keep the seams enforced

## Architecture

### Repository Layout

This repository (campus-suite) holds the three services, the yapper event
bus, the migrations, the gateway, and the contract/sanity harness. Every
shared layer was carved into its own repository (the #970 arc, closed
2026-11-04); the suite declares them as version-pinned wheel URLs in the
root `pyproject.toml` and relocks deliberately.

### Branch Strategy

```
weekly → staging → main
```
- **`weekly`**: Active development, expected breakage
- **`staging`**: Extended testing, pre-production validation
- **`main`**: Stable, production-ready releases

## Dependency Rules

```
auth, api, audit → services, storage, webauth, model, common,
                   flask_campus (consumer layer), deploy
storage → model, common               (campus-core)
webauth → model, common               (campus-core)
services → common                     (campus-core)
flask_campus, audit.middleware/client/http/roles → common, model
                                      (flask-campus; never imports services)
yapper → (nothing — self-contained)
deploy → flask-campus, common         (campus-deploy)
```

**Key Constraints:**
- `auth` and `api` contain business logic in `.resources` submodules
- The shared layers are external distributions, each enforced by its own
  repo's boundary guard: campus-common (stdlib + bcrypt only),
  campus-model (stdlib + common), campus-core (no service imports,
  drivers lazy), flask-campus (never imports services)
- The direction is one-way: services import the layers above them,
  never the reverse

## Namespace Package Rules (PEP 420)

The `campus` import namespace is a **native namespace package**: no
distribution ships a `campus/__init__.py`. Python merges every `campus/`
directory found on `sys.path` into one virtual package, so each
distribution owns its own subtree and consumers import one flat namespace:

- `campus-suite` (this repo) ships `campus/auth/`, `campus/api/`, `campus/audit/` (service half), `campus/yapper/`
- `campus-common` ships `campus/common/`
- `campus-model` ships `campus/model/`
- `flask-campus` ships `campus/flask_campus/` + the app-facing `campus/audit/{middleware,client,http,roles}/`
- `campus-deploy` ships `campus/deploy.py`
- `campus-core` ships `campus/storage/`, `campus/webauth/`, `campus/services/`

`campus.audit` is a **shared subnamespace**: the suite owns its
`__init__.py` (the audit service's `init_app`) via `pkgutil.extend_path`,
while flask-campus contributes the app-facing halves — disjoint
subpackages, so the merge is safe.

Rules:

- Never add `campus/__init__.py` to any distribution. One stale regular
  package shadows every other dist's portions **silently** — imports
  resolve from the wrong place with no error at install time.
- Each distribution's own subpackages (`campus/common/`, `campus/auth/`,
  ...) remain regular packages with their own `__init__.py`; only the
  shared ancestor level is init-less.
- After `poetry build`, audit the wheels:

  ```bash
  python scripts/audit_wheel_namespace.py
  ```

- When upgrading environments across this conversion, rebuild venvs
  instead of layering installs: leftover `campus/` directories or
  `__pycache__`-only portion dirs from older installs keep serving stale
  imports under the merged namespace.

The `campus_python` client library uses a separate top-level namespace and
is unaffected by these rules.

## Installation

### For app authors (classroom/admin/profile/nyxchange-style apps)

Apps install the consumer dists and **never** campus-suite:

```toml
[tool.poetry.dependencies]
flask = "^3.0.0"
campus-common = {url = "https://github.com/nyjc-computing/campus-common/releases/download/v0.3.1/campus_common-0.3.1-py3-none-any.whl"}
flask-campus = {url = "https://github.com/nyjc-computing/flask-campus/releases/download/v0.1.3/flask_campus-0.1.3-py3-none-any.whl"}
campus-api-python = {url = "https://github.com/nyjc-computing/campus-api-python/releases/download/v0.6.0/campus_api_python-0.6.0-py3-none-any.whl"}
```

Import paths are unchanged from the monorepo era — the portions merge
(`from campus.flask_campus import OAuthLoginManager`,
`from campus.audit.middleware import init_app`).

### For the suite (this repo's deploy targets)

The suite declares every dist it consumes as a version-pinned wheel URL
(see the root `pyproject.toml`) plus its direct driver pins
(psycopg2/pymongo/boto3 — campus-core's drivers are extras, and the
suite needs all three).

### Bumping a dist

Edit the wheel URL to the new release tag, run `poetry lock`, and read
that release's CHANGELOG first (strict-0.x: pre-1.0 minors may break).
Direct-URL pins bake the exact wheel into your lockfile — never re-cut a
release someone pins (it invalidates every consumer lock). Direct
declaration is required only for repos that import the package
themselves; otherwise the transitive pin from campus-suite (or
flask-campus) suffices — but a direct pin at a DIFFERENT version than
the baked one is a version-solving conflict, so bump direct pins in the
same relock that takes a new transitive version.

### Client Library Installation

The SDK ships versioned wheels like every other dist (sdk#137). Pin the
release wheel by URL (the import package is `campus_python`):

```toml
campus-api-python = {url = "https://github.com/nyjc-computing/campus-api-python/releases/download/v0.6.0/campus_api_python-0.6.0-py3-none-any.whl"}
```

Cut an SDK release by pushing an annotated `v*` tag on campus-api-python:
CI builds the wheel and attaches it to the GitHub release (the tag
annotation is the release body). Read that release's notes before
bumping — strict-0.x minors are breaking. Note flask-campus's wheel
metadata pins a specific SDK wheel URL, so an SDK bump requires a
flask-campus rebuild (relock both together).

## Building and Validation

### Local Development

```bash
# Install dependencies
poetry install

# Test imports
poetry run python -c "import campus.auth, campus.api, campus.storage, campus.model"

# Run tests
poetry run python tests/run_tests.py unit
```

### Release Process

1. **Development**: Work in `weekly` branch
2. **Integration**: Merge `weekly` → `staging` for extended testing
3. **Release**: Merge `staging` → `main` when stable
4. **Tagging**: Create version tags on `main` branch

### Dependency Updates

Update dependencies in root `pyproject.toml`:

```bash
# Update a specific package
poetry add requests@^2.31.0

# Update all packages
poetry update

# Lock dependencies
poetry lock
```

## Troubleshooting

### Import Errors

Ensure you're using `poetry run python` instead of system Python.

### Dependency Conflicts

Direct-URL deps bake their wheel hash and source URL into metadata: two
dists must never ship the same module (shared-namespace RECORD overlap),
and a consumer's direct pin at an older version than a transitive pin is
a version-solving conflict — bump the direct pin to match, then
`poetry lock`.

### Authentication Issues

Verify GitHub access for private repositories:
```bash
git config --global url."https://username:token@github.com/".insteadOf "https://github.com/"
```

### Validation Commands

```bash
# Check environment
poetry env info

# Test installation
poetry run python -c "import campus"

# Test modules
poetry run python -c "import campus.auth; import campus.api; import campus.storage"
```

## Why Version-Pinned Wheels?

Shared layers are consumed as release wheels pinned by URL: reproducible
builds, explicit per-repo bump decisions, and no PyPI publishing delays.
The client SDK (campus_python — outside the `campus` namespace) is
published the same way: versioned wheels pinned by URL (sdk#137). When
the ecosystem stabilizes at 1.0.0, dists can move to PyPI with real
range constraints.
