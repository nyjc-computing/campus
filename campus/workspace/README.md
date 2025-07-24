# Campus Workspace

A meta-package that provides the complete Campus ecosystem as a single deployable unit, solving Poetry version compatibility issues while maintaining modular development practices.

## Overview

`campus.workspace` is designed to bridge the gap between modular development and simplified deployment. It bundles all Campus services into a single package that works with any Poetry version, including older versions used by hosting platforms like Replit.

## Problem Statement

Modern Python packaging features can create deployment challenges:

- **Poetry Version Conflicts**: Older Poetry versions (< 1.5) don't support `package-mode = false`
- **Complex Dependencies**: Individual package dependencies can cause deployment failures
- **Platform Limitations**: Hosting platforms often use older tooling versions
- **Configuration Switching**: Managing different configs for dev vs deployment is error-prone

## Solution

Campus Workspace consolidates all services into a single meta-package:

- ✅ **Universal Compatibility**: Works with any Poetry version
- ✅ **Consolidated Dependencies**: All dependencies in one `pyproject.toml`
- ✅ **Simplified Deployment**: No special configuration needed
- ✅ **Preserved Modularity**: Individual packages maintained for development

## Architecture

### Package Structure

```
campus/
├── workspace/          # 📦 THIS PACKAGE - Meta-package for deployment
├── common/            # 🛠️ Foundational utilities and integration configs
├── vault/             # 🔐 Secure credential and secret management
├── storage/           # 💾 Database backends (MongoDB, PostgreSQL)
├── client/            # 🔌 External API integration libraries
├── models/            # 🏛️ Data models and schemas
└── apps/              # 🌐 Web applications and services
```

### Import Strategy

The workspace package imports and re-exports all Campus modules:

```python
# All Campus packages available through campus namespace
from campus import common
from campus import vault  
from campus import storage
from campus import client
from campus import models
from campus import apps
```

## Installation

This is the recommended way to install all Campus services and dependencies for a complete deployment.

**Recommended installation method:**

```bash
bash install.sh
```

This script will build and install all required subpackages in the correct order.

> **Note:** Do not use `pip install` or `poetry install` directly for this meta-package unless you are developing locally. The install script ensures all dependencies are present and compatible.

## Usage

### Complete System Import

```python
# Import the entire Campus ecosystem
import campus.workspace

# All services now available via campus namespace
user = campus.models.User(...)
vault_client = campus.client.vault
storage_backend = campus.storage.get_backend("postgresql")
```

### Selective Module Import

```python
# Import only what you need
from campus import models, vault, storage
from campus.apps import factory

# Use services directly
user = models.User(username="student123")
secret = vault.get_secret("database_url")
db = storage.connect("main")
app = factory.create_app()
```

### Service Integration

```python
# Full-stack application example
from campus import apps, vault, storage, models

# Initialize the complete system
app = apps.create_app()
vault.init_app(app)
storage.init_app(app)
models.init_app(app)

# Ready for deployment
if __name__ == "__main__":
    app.run()
```

## Development vs Deployment

### Development Workflow

**Individual Package Development**:
```bash
# Work on specific services
cd campus/vault && poetry install
cd campus/models && poetry install

# Test individual components
python -m pytest campus/vault/tests/
python -m pytest campus/models/tests/
```

**Modular Benefits**:
- Fast iteration on specific services
- Clear separation of concerns
- Easy onboarding for junior developers
- Independent testing and deployment

### Deployment Workflow

**Single Package Deployment**:
```bash
# Install complete system
poetry install

# Deploy everything together
python -m campus.workspace
```

**Deployment Benefits**:
- Works with any Poetry version
- Single dependency resolution
- Simplified configuration
- Platform compatibility

## Dependencies

### Consolidated Requirements

All dependencies from individual packages are consolidated:

```toml
[tool.poetry.dependencies]
python = ">=3.11.0,<3.12"

# Web framework
flask = "^3.0.0"
gunicorn = "^21.2.0"
werkzeug = "^3.0.0"

# Database drivers
psycopg2-binary = "^2.9.0"  # PostgreSQL
pymongo = {extras = ["srv"], version = "^4.8.0"}  # MongoDB

# Security and utilities
bcrypt = "^4.2.1"
requests = "^2.32.4"
```

### Version Management

- **Python**: 3.11+ required for modern typing features
- **Flask**: 3.0+ for latest security and performance improvements
- **Database**: Production-ready drivers with connection pooling
- **Security**: Industry-standard cryptographic libraries

## Platform Compatibility

### Supported Platforms

- ✅ **Replit**: Works with older Poetry versions
- ✅ **Heroku**: Standard Python buildpack support
- ✅ **Railway**: Modern deployment platform
- ✅ **Vercel**: Serverless Python functions
- ✅ **DigitalOcean**: App Platform and Droplets
- ✅ **AWS**: Lambda, ECS, EC2
- ✅ **Google Cloud**: Cloud Run, App Engine
- ✅ **Local Development**: Any environment with Python 3.11+

### Configuration

Environment variables for cross-platform configuration:

```bash
# Database connections
export VAULTDB_URI="postgresql://..."
export STORAGE_URI="postgresql://..."

# Authentication
export CLIENT_ID="your_client_id"
export CLIENT_SECRET="your_client_secret"
# SECRET_KEY now stored in vault under 'campus' label - no environment variable needed

# Optional: Service-specific configs
export FLASK_ENV="production"
export LOG_LEVEL="INFO"
```

## Deployment Examples

### Replit

```python
# main.py
import campus.workspace
from campus.apps import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

### Heroku

```python
# app.py
import campus.workspace
from campus.apps import create_app

app = create_app()
# Heroku will use gunicorn automatically
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

COPY . .
CMD ["python", "-m", "campus.workspace"]
```

### AWS Lambda

```python
# lambda_function.py
import campus.workspace
from campus.apps import create_app

app = create_app()

def lambda_handler(event, context):
    # AWS Lambda handler
    return app.process_lambda_event(event, context)
```

## Development Guidelines

### Adding New Services

1. **Create Individual Package**: Develop in `campus/{service}/`
2. **Add to Workspace**: Import in `campus/workspace/__init__.py`
3. **Update Dependencies**: Add to `campus/workspace/pyproject.toml`
4. **Test Integration**: Verify imports work correctly

### Maintaining Compatibility

1. **Keep Dependencies Minimal**: Only include production requirements
2. **Use Stable Versions**: Avoid pre-release or unstable packages
3. **Test Across Platforms**: Verify deployment works on target platforms
4. **Document Changes**: Update this README when adding services

### Migration Strategy

For existing deployments using individual packages:

```python
# Old way (multiple packages)
from campus.vault import create_app as vault_app
from campus.apps import create_app as main_app

# New way (workspace)
import campus.workspace
from campus import vault, apps

vault_app = vault.create_app()
main_app = apps.create_app()
```

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure workspace is properly installed
poetry install
python -c "import campus.workspace; print('✅ Workspace installed')"
```

**Missing Dependencies**:
```bash
# Check all dependencies are available
poetry show
poetry check
```

**Version Conflicts**:
```bash
# Clear cache and reinstall
poetry env remove python
poetry install
```

### Platform-Specific Issues

**Replit**: Ensure `.replit` file points to workspace entry point
**Heroku**: Verify `Procfile` uses correct app module
**Lambda**: Check handler function is properly exported

## Version History

- **0.1.0**: Initial workspace package with core services
- Future versions will add more services and platform integrations

## Contributing

1. **Individual Development**: Work on services in their own packages
2. **Integration Testing**: Test workspace imports after changes
3. **Dependency Management**: Update workspace `pyproject.toml` for new deps
4. **Platform Testing**: Verify deployments work on target platforms
5. **Documentation**: Update README for new services or deployment targets

## License

Same as main Campus project license.
