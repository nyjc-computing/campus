# Campus Deployment - Ultra Simple

One codebase, one `main.py`, two deployment modes. 
Clients use `campus.client` library to communicate with deployments via HTTP API.

## 🔐 Deploy Vault Service

```bash
# Install with vault dependencies
poetry install --extras vault

# Configure deployment mode
echo 'vault' > deploy
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
echo 'apps' > deploy
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

## 🎯 Replit Instructions

**For Vault:**
1. In Shell: `echo 'vault' > deploy`
2. Click Run button (or `python main.py`)

**For Apps:**
1. In Shell: `echo 'apps' > deploy`
2. Click Run button (or `python main.py`)

**No pyproject.toml switching needed!** 

## 📁 How It Works

- `deploy` file contains either "vault" or "apps" (gitignored)
- `main.py` reads the file and starts the appropriate service
- Missing or invalid `deploy` file defaults to "apps"

**Valid deploy modes:** `vault`, `apps`

That's it!
