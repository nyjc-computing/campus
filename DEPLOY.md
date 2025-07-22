# Campus Deployment - Ultra Simple

One codebase, one `main.py`, two deployment modes. 
Clients use `campus.client` library to communicate with deployments via HTTP API.

## 🔐 Deploy Vault Service

```bash
# Install with vault dependencies
poetry install --extras vault

# Configure deployment mode
export DEPLOY=vault
python main.py
```

**What you get:**
- Vault API: `/health`, `/vaults`, `/vault/<label>/<key>`
- Minimal service for credential management
- Lightweight deployment with only vault dependencies

## 🚀 Deploy Full Apps

```bash  
# Install with apps dependencies
poetry install --extras apps

# Configure deployment mode  
export DEPLOY=apps
python main.py
```

**What you get:**
- Complete Campus web application
- All features and API endpoints
- Full deployment with all app dependencies

## 📚 Client Library Usage

The `campus.client` library can be installed independently:

```bash
# Minimal installation for client usage only
poetry install  # Only installs requests + client code

# Use in your code
from campus.client.vault import VaultClient
from campus.client.users import UsersClient
```

## 🎯 Platform Instructions

### Railway
Set environment variable in Railway dashboard:
- `DEPLOY=vault` or `DEPLOY=apps`
- Start command: `gunicorn --bind "0.0.0.0:$PORT" wsgi:app`

### Replit
In Secrets tab, add:
- Key: `DEPLOY`
- Value: `vault` or `apps`

Then click Run button (or `python main.py`)

### Local Development
```bash
# Vault mode
export DEPLOY=vault
python main.py

# Apps mode  
export DEPLOY=apps
python main.py
```

## 📁 How It Works

- `DEPLOY` environment variable contains either "vault" or "apps"
- `main.py` reads the environment variable and starts the appropriate service
- Missing `DEPLOY` variable defaults to "apps"
- For production, use `wsgi.py` with Gunicorn

**Valid deploy modes:** `vault`, `apps`

That's it!
