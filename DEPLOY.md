# Campus Deployment - Ultra Simple

One codebase, one `main.py`, two deployment modes.

## 🔐 Deploy Vault Service

```bash
echo 'vault' > deploy
python main.py
```

**What you get:**
- Vault API: `/health`, `/vaults`, `/vault/<label>/<key>`
- Minimal service for credential management
- ~200MB deployment (includes all deps but only runs vault)

## 🚀 Deploy Full Apps

```bash  
echo 'apps' > deploy
python main.py
```

**What you get:**
- Complete Campus web application
- All features and API endpoints
- ~200MB deployment

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
