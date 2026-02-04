# Campus Deployment - Ultra Simple

One codebase, one `main.py`, multiple deployment modes. 
Clients use the `campus_python` library to communicate with deployments via HTTP API.

## 🔐 Deploy Auth Service

```bash
# Install with dependencies
poetry install

# Configure deployment mode
export DEPLOY=campus.auth
python main.py
```

**What you get:**
- Authentication API: OAuth, session management, credentials
- Client authentication and authorization
- Minimal service for auth operations

## 🌐 Deploy API Service

```bash  
# Install with dependencies
poetry install

# Configure deployment mode  
export DEPLOY=campus.api
python main.py
```

**What you get:**
- RESTful API endpoints for Campus resources
- Circle management, Email OTP, etc.
- Full API deployment

## 📚 Client Library Usage

The `campus_python` client library is installed separately:

```bash
# Install campus_python client
poetry add git+https://github.com/nyjc-computing/campus-api-python.git@main

# Use in your code
import campus_python
campus = campus_python.Campus()
```

See the [campus-api-python repository](https://github.com/nyjc-computing/campus-api-python) for documentation.

## 🎯 Platform Instructions

### Railway
Set environment variable in Railway dashboard:
- `DEPLOY=campus.auth` or `DEPLOY=campus.api`
- Start command: `gunicorn --bind "0.0.0.0:$PORT" --timeout 120 wsgi:app`

**Note:** The `--timeout 120` flag sets a 2-minute timeout (vs default 30s) to handle OAuth flows and external API calls.

### Replit
In Secrets tab, add:
- Key: `DEPLOY`
- Value: `campus.auth` or `campus.api`

Then click Run button (or `python main.py`)

### Local Development
```bash
# Auth service
export DEPLOY=campus.auth
python main.py

# API service  
export DEPLOY=campus.api
python main.py
```

## 📁 How It Works

- `DEPLOY` environment variable specifies the service module to deploy (e.g., `campus.auth`, `campus.api`)
- `main.py` reads the environment variable and starts the appropriate service
- For production, use `wsgi.py` with Gunicorn or other WSGI servers

**Valid deploy modes:** `campus.auth`, `campus.api`, or any module with `init_app()`

That's it!
