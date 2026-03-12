# campus.flask_campus

Common utility functions for Flask request/response validation and OAuth login management.

## Installation

```python
from campus.flask_campus import (
    HtmlResponse,
    JsonResponse,
    OAuthLoginManager,
    get_user_agent,
    get_request_headers,
    get_request_payload,
    unpack_into,
    unpack_request,
    validate_request_and_extract_json,
    validate_request_and_extract_urlparams,
    validate_json_response,
)
```

## OAuth Login Manager

The `OAuthLoginManager` provides seamless OAuth authentication integration with Flask using the Campus Admin Portal.

### Basic Setup

```python
from flask import Flask
from campus.flask_campus import OAuthLoginManager

app = Flask(__name__)
app.secret_key = "your-secret-key"

# Initialize the login manager
login_manager = OAuthLoginManager(
    campus_client=None,  # Uses default Campus client
    default_endpoint="index"  # Redirect here after login/logout
)
login_manager.init_app(app)

@app.route("/")
def index():
    return "Welcome!"
```

### Using a Custom Campus Client

```python
import campus_python

campus = campus_python.Campus(timeout=60)
login_manager = OAuthLoginManager(
    campus_client=campus,
    default_endpoint="dashboard"
)
login_manager.init_app(app)
```

### Protecting Routes

Use the `@login_manager.login_required` decorator to protect routes that require authentication:

```python
@app.route("/dashboard")
@login_manager.login_required
def dashboard():
    # Access the authenticated user via flask.g.user
    return f"Hello, {flask.g.user}"
```

### Authentication Endpoints

Once initialized, the following endpoints are automatically available:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/login` | GET | Initiates OAuth login flow. Accepts optional `?next=/path` parameter for post-login redirect |
| `/finalize_login` | GET | OAuth callback endpoint (internal use) |
| `/logout` | GET | Signs out from Campus Admin Portal |

### Authentication Flow

1. User visits a protected route
2. Redirected to `/login` (with original path saved in `next` parameter)
3. Redirected to Campus OAuth authorization page
4. After successful authorization, redirected to `/finalize_login`
5. Access token is stored and login session is created (30-day expiry)
6. Redirected to the original destination

## Request/Response Utilities

### `unpack_request`

Decorator that automatically unpacks Flask request data into function arguments based on type annotations.

- **GET requests**: Uses URL parameters
- **POST/PUT requests**: Uses JSON body

```python
from campus.flask_campus import unpack_request

@app.get("/search")
@unpack_request
def search(query: str, limit: int = 10):
    # query and limit are automatically extracted from URL params
    return {"results": [], "limit": limit}

@app.post("/users")
@unpack_request
def create_user(email: str, name: str, is_active: bool = False):
    # email, name, is_active are extracted from JSON body
    return {"email": email, "name": name, "is_active": is_active}
```

**Requirements:**
- All parameters must have type annotations
- Parameters must be keyword-argument compatible (no positional-only parameters)
- Missing required parameters raise `ValidationError`

### `unpack_into`

Manually unpack request arguments into a function's arguments.

```python
from campus.flask_campus import unpack_into

def process_data(name: str, count: int = 1):
    return {"name": name, "count": count}

# Unpack request data into the function
result = unpack_into(process_data, **request_args)
```

### `get_request_payload`

Extract JSON payload or URL parameters from the current Flask request.

```python
from campus.flask_campus import get_request_payload

@app.post("/process")
def process():
    data = get_request_payload()  # Returns dict
    # For GET requests: returns URL params
    # For POST requests: returns JSON body
```

### `get_request_headers`

Get request headers as a `campus.model.HttpHeader` dictionary.

```python
from campus.flask_campus import get_request_headers

@app.before_request
def log_headers():
    headers = get_request_headers()
    # Returns campus.model.HttpHeader (dict-like)
```

### `get_user_agent`

Get the User-Agent header from the current request.

```python
from campus.flask_campus import get_user_agent

@app.route("/info")
def info():
    ua = get_user_agent()
    return f"User-Agent: {ua}"
```

## Validation Utilities

### `validate_request_and_extract_json`

Validate request JSON body against a schema.

```python
from campus.flask_campus import validate_request_and_extract_json

def on_error(status, message):
    from flask import jsonify
    return jsonify({"error": message}), status

@app.post("/submit")
def submit():
    schema = {"title": str, "count": int}
    data = validate_request_and_extract_json(schema, on_error=on_error)
    # data is validated
    return {"status": "ok"}
```

### `validate_request_and_extract_urlparams`

Validate URL parameters against a schema.

```python
from campus.flask_campus import validate_request_and_extract_urlparams

@app.get("/search")
def search():
    schema = {"q": str, "page": int}
    params = validate_request_and_extract_urlparams(
        schema,
        on_error=on_error,
        strict=True  # All schema keys required
    )
    return params
```

### `validate_json_response`

Validate response JSON against a schema.

```python
from campus.flask_campus import validate_json_response
import requests

resp = requests.get("https://api.example.com/data")
schema = {"id": int, "name": str}

validate_json_response(
    schema,
    resp.json(),
    on_error=on_error,
    ignore_extra=True,
    error_status_code=502,
    error_message="External API error"
)
```

## Types

Type definitions for type hinting:

| Type | Definition |
|------|------------|
| `HtmlResponse` | `tuple[str, int]` |
| `JsonResponse` | `tuple[dict[str, Any], int]` |
| `JsonObject` | `dict[str, Any]` |
| `StatusCode` | `int` |

## Error Handling

The utilities raise standard errors:

- `ValidationError` - Raised when validation fails with structured field errors
- `InvalidRequestError` - Raised for malformed JSON payloads
- `RuntimeError` - Raised when functions are called outside a Flask request context

```python
from campus.common.errors import ValidationError, FieldError

try:
    data = get_request_payload()
except ValidationError as e:
    # e.errors contains list of FieldError objects
    for error in e.errors:
        print(f"{error.field}: {error.message} ({error.code})")
```
