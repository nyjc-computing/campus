# Campus Client Configuration

This document explains how to configure base URLs for different Campus service deployments.

## Overview

The campus client system supports multiple deployments with different base URLs. Instead of hardcoding URLs, you can specify them via environment variables or explicitly when creating client instances.

## Environment Variables

Set these environment variables to configure base URLs for your deployment:

```bash
# Apps services (circles, users, emailotp, clients)
export CAMPUS_APPS_BASE_URL="https://your-apps-deployment.example.com"

# Vault services (vault, vault_access, vault_client)  
export CAMPUS_VAULT_BASE_URL="https://your-vault-deployment.example.com"
```

## Default URLs

If environment variables are not set, the client will use these default URLs:
- Apps: `https://api.campus.nyjc.dev`
- Vault: `https://vault.campus.nyjc.dev`

## Manual URL Specification

You can also specify base URLs explicitly when creating client instances:

```python
from campus.client.circles import CirclesClient
from campus.client.vault import VaultClient

# Specify custom base URLs
circles = CirclesClient(base_url="https://custom-apps.example.com")
vault = VaultClient(base_url="https://custom-vault.example.com")
```

## Service Mappings

The following services are mapped to each deployment:

**Apps Deployment:**
- circles
- users
- emailotp
- clients

**Vault Deployment:**
- vault
- vault_access
- vault_client

## Examples

### Production Environment
```bash
export CAMPUS_APPS_BASE_URL="https://api.campus.nyjc.dev"
export CAMPUS_VAULT_BASE_URL="https://vault.campus.nyjc.dev"
```

### Staging Environment
```bash
export CAMPUS_APPS_BASE_URL="https://api-staging.campus.nyjc.dev"
export CAMPUS_VAULT_BASE_URL="https://vault-staging.campus.nyjc.dev"
```

### Local Development
```bash
export CAMPUS_APPS_BASE_URL="http://localhost:8000"
export CAMPUS_VAULT_BASE_URL="http://localhost:8001"
```

### Split Deployment (Future)
If you need to split services across more deployments:

```bash
export CAMPUS_APPS_BASE_URL="https://api.campus.nyjc.dev"
export CAMPUS_VAULT_BASE_URL="https://vault.campus.nyjc.dev"
# Future: additional services could use different URLs
```

You would need to update the service mappings in `campus/client/config.py` to support additional deployments.
