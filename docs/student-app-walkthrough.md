# Building a Student App on Campus — a from-zero walkthrough

This walkthrough takes you from an empty repository to a deployed Flask app
whose users **sign in with their NYJC account through Campus** and call Campus
APIs with their credentials. It is written for app authors — the student
projects on the platform (the nyxchange-timetable-v2 / campus-profile mold) and
any first-party app that follows.

If you came here to work **on Campus itself**, you want
[GETTING-STARTED.md](GETTING-STARTED.md) instead. This page is the connective
tissue between the pieces; wherever a step has a dedicated guide, it links out
rather than repeating it.

**Reference app:** [campus-classroom](https://github.com/nyjc-computing/campus-classroom)
is the most complete example of everything below — SSO, scoped API calls,
upstream (Google) tokens via the broker, audit journeys, and a Railway
deployment. Skim its `apps/classroom/__init__.py` next to this page.

## 0. What you are building

```
browser ──> your app (Flask)
              │  sign-in seam (flask_campus)
              ▼
           campus.auth  ── NYJC identity, tokens, sessions
              │
              ▼
           Campus APIs  ── your app calls them as the signed-in user
```

Your app never sees a password and never runs its own OAuth flow. Campus owns
identity; your app owns its features. Three building blocks:

| Piece | Where it lives | What it gives you |
|---|---|---|
| `campus-suite` (the `campus` package) | [campus](https://github.com/nyjc-computing/campus) | `flask_campus` login manager, shared models |
| `campus-api-python` (the `campus_python` package) | [campus-api-python](https://github.com/nyjc-computing/campus-api-python) | the typed API client (`Campus(...)`) |
| your OAuth client record | campus.auth | `CLIENT_ID` / `CLIENT_SECRET` for your app |

## 1. Scaffold the repository

Poetry project with Flask and the two Campus packages — copy the dependency
block from campus-classroom's `pyproject.toml`:

```toml
[tool.poetry.dependencies]
python = ">=3.11,<3.14"
flask = "^3.0.0"
python-dotenv = "^1.2.1"

campus-api-python = {git = "https://github.com/nyjc-computing/campus-api-python.git", branch = "main"}
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "weekly"}
```

For the dev container, copy the shared template rather than inventing one
([devcontainer-flask](https://github.com/nyjc-computing/campus-devcontainer-flask)):

```bash
cp -r ../campus-devcontainer-flask/.devcontainer your-app/.devcontainer
```

The post-create script installs Poetry and runs `poetry install` for you.

## 2. Register your app with Campus (client credentials)

Your app authenticates to campus.auth as an OAuth **client**. Register it and
its exact redirect URI **before** attempting login — `redirect_uri` matching is
fail-closed, and a client with no registered URIs can never authorize
([why](auth-login-flow.md#gotchas-for-implementers), gotcha 2).

Preview the registration with the CLI's dry-run, then run it for real against
the dev deployment:

```bash
campus client new --name "My App" --description "My application" --dry-run
```

Record the issued `CLIENT_ID` / `CLIENT_SECRET`. The redirect URI to register
is `<your PUBLIC_URL>/finalize_login`.

## 3. Wire sign-in with `flask_campus`

`flask_campus.OAuthLoginManager` implements the whole
[client-side checklist](auth-login-flow.md#client-side-checklist) of the
browser login flow — session creation, `/authorize` handoff, the
`/finalize_login` code exchange, token storage in the Flask session, and
refresh — so your app code stays three lines:

```python
import flask
from campus_python import Campus
from campus import flask_campus

def create_app():
    app = flask.Flask(__name__)
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    campus = Campus(...)          # resolves service URLs from env
    login_manager = flask_campus.OAuthLoginManager(
        campus_client=campus,
        default_endpoint="index",  # where users land after login
    )
    login_manager.init_app(app)    # registers /login, /finalize_login, /logout

    app.campus = campus
    app.login_manager = login_manager

    @app.get("/")
    def index():
        return flask.render_template("index.html")

    @app.get("/dashboard")
    @login_manager.login_required      # anonymous visitors -> /login
    def dashboard(**_):
        return flask.render_template("dashboard.html")

    return app
```

Your "Sign in with NYJC Account" button is just a link to `/login`. Protected
views take `login_required`; the signed-in user is `flask.g.user` afterwards.

What to know before you ship this seam:

- **Request minimal scopes** on session creation — the consent screen is not
  yet interactive, so whatever you request is granted as-is (gotcha 6).
- **`PUBLIC_URL` must be exact.** Every absolute redirect URL derives from it;
  a wrong value breaks the identity handoff with origin mismatches (gotcha 7,
  and [#653](https://github.com/nyjc-computing/campus/issues/653)). Set it in
  dev *and* production.
- The protocol under the seam — the six-step exchange, token lifecycle, and
  the sign-out chain — is documented in
  [auth-login-flow.md](auth-login-flow.md). Read it when something breaks, not
  before.

## 4. Call Campus APIs as the signed-in user

Inside a request, open a user session and use the typed client; the 401
auto-refresh hook keeps long sessions alive:

```python
with campus.with_user_session(refresh_on_401=True) as client:
    assignments = client.api.assignments.list(created_by=flask.g.user.id)
```

- The client library knows the
  [URL trailing-slash schema](campus-api-schema.md#url-trailing-slash-convention)
  so you don't have to; if you ever hand-build a URL, follow that page.
- To probe an endpoint from your terminal while developing, use
  `campus-cli <command> --dry-run` to see the exact request first.
- nyxchange's open SSO items (e.g. its `finalize_login` 500) are good examples
  of the class of bug this seam can have — deploy the walkthrough's exact
  env vars before debugging deeper.

## 5. Upstream tokens (Google, …) — use the broker, not your own OAuth

If your app needs an upstream provider token (Google Classroom, Drive, …),
**do not register your own OAuth client with the provider**. Campus brokers
upstream access tokens to signed-in users:

1. Users **connect** once via the campus-profile integrations page.
2. Your app **releases** tokens on demand from
   `POST /auth/v1/broker/<provider>/[<integration>/]` with `min_scopes`.
3. A missing connection (404) or missing scopes (403) both remediate through
   the same connect flow.

The contract you sign up to (invariant D — no persistence, treat as a secret)
and the full integration-app pattern are documented in
[token-broker.md](token-broker.md#the-integration-app-pattern-campus-classroom).

## 6. Sign-out

Link users to `/logout` (provided by the login manager). It ends the **Campus**
session server-side and clears the app session; it does not sign the user out
of Google — the identity leg always shows the account chooser on re-login.
Details: [sign-out chain](auth-login-flow.md#sign-out-chain-785788791).

## 7. Debugging with `campus.audit`

When your app misbehaves in a deployment, the audit trail is the shared
observability surface:

- **Enable it** on your app: set `AUDIT_API_KEY` (a `audit_v1_` key minted by
  the campus operator) plus `AUDIT_TRACING_ENABLED=1`, then look at your
  requests in the audit UI (`/audit/`). Full setup:
  [audit-tracing.md](audit-tracing.md#enabling-on-a-deployment).
- **Name your journeys** so your app's actions are readable in traces:
  `@flask_campus.journey("myapp.thing.do")` on the route (see
  [action journeys](audit-tracing.md#action-journeys-828)).
- Ingestion is fail-safe — a wrong key loses spans, never requests — so
  enabling it can't take your app down.

## 8. Deploy

The platform default is Railway (see each service's README and
[DEPLOY.md](DEPLOY.md) for the campus side). For your app, the environment
contract in production is the same as dev, plus exact values:

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Flask session signing — generate, don't share |
| `CLIENT_ID` / `CLIENT_SECRET` | from step 2 |
| `PUBLIC_URL` | the exact canonical origin Railway serves (step 3) |
| `AUDIT_API_KEY` | optional, enables step 7 |

Deploy, click Sign in, and you have a student app on Campus.

## Where to go next

- [campus-classroom](https://github.com/nyjc-computing/campus-classroom) — the
  reference integration app (SSO + broker + journeys + deploy).
- [auth-login-flow.md](auth-login-flow.md) — the login protocol under
  `flask_campus`.
- [token-broker.md](token-broker.md) — upstream tokens without your own OAuth.
- [audit-tracing.md](audit-tracing.md) — traces, journeys, and API keys.
- [campus-api-schema.md](campus-api-schema.md) — URL rules for every resource.
