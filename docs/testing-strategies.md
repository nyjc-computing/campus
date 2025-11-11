# Campus Testing Strategies

This document outlines the three primary testing strategies available in the Campus project. Each strategy provides different levels of integration and serves specific testing goals.

## Table of Contents

- [Overview](#overview)
- [Recommended Entry Points](#recommended-entry-points)
- [Strategy 1: Development Server Testing](#strategy-1-development-server-testing)
- [Strategy 2: Local Service Testing](#strategy-2-local-service-testing)
- [Strategy 3: Flask Test Client Testing](#strategy-3-flask-test-client-testing)
- [When to Use Each Strategy](#when-to-use-each-strategy)
- [Test Suite Execution](#test-suite-execution)
- [Quick Reference](#quick-reference)

## Overview

Campus provides three testing strategies:

| Strategy | Environment | Data | Network | Use Case |
|----------|-------------|------|---------|----------|
| **Development Server** | Remote (Railway) | Simulated | Real HTTP | Manual testing |
| **Local Services** | Local background | Test data | Real HTTP | Integration (broken) |
| **Flask Test Client** | In-process | Test data | No network | Unit/component |

**Note**: Local Services strategy currently broken after auth/api refactor.

All strategies use the same Campus client interface.

## Entry Points

- **Local Services**: `tests.fixtures.services.init()` (currently broken)
- **Flask Test Client**: `tests.flask_test.create_test_client_from_manager()`
- **Development Server**: Set `ENV=development`, use `Campus()`

## Strategy 1: Development Server Testing

**Purpose**: Test against live development services with simulated real data.

### Environment
- **Auth**: `https://campus-auth-development.up.railway.app/`
- **API**: `https://campus-api-development.up.railway.app/`
- **Data**: Simulated (non-production)
- **Network**: Real HTTP

### Usage

```python
import campus_python
from campus.common import env

env.ENV = 'development'
campus = campus_python.Campus()

# Requests go to Railway
secret = campus.auth.vaults["deployment"]["key"]
```

### When to Use
- ✅ Manual testing
- ✅ Demos
- ✅ Deployment verification
- ❌ CI/CD (requires internet)
- ❌ Unit tests (slow)

## Strategy 2: Local Service Testing

**Status**: Currently broken after auth/api refactor.

**Purpose**: Run services locally in background for integration testing.

### Environment
- **Services**: Local Flask apps in background
- **Data**: Test databases (PostgreSQL, MongoDB)
- **Network**: HTTP to localhost
- **Cleanup**: Automatic

### Setup (when fixed)

```python
from tests.fixtures import services, postgres, mongodb
import campus_python

# Purge databases
postgres.purge_database("authdb")
mongodb.purge_database("storagedb")

# Start services
with services.init() as manager:
    campus = campus_python.Campus()
    
    # Test against local services
    secret = campus.auth.vaults["test"]["key"]
```

### Service Dependencies
1. **Auth** → Creates credentials
2. **Yapper** → Requires auth
3. **API** → Requires auth + yapper

### When to Use (when fixed)
- ✅ Integration testing
- ✅ Service interactions
- ✅ CI/CD
- ❌ Unit tests (too heavy)

## Strategy 3: Flask Test Client Testing

**Purpose**: Test with in-process Flask apps (no network).

### Environment
- **Services**: Flask app instances
- **Data**: In-memory SQLite, Python dicts
- **Network**: None
- **Speed**: Fastest

### Setup

```python
from tests.flask_test import create_test_client_from_manager
from tests.fixtures import services

with services.init() as manager:
    client = create_test_client_from_manager(manager)
    
    # No network calls
    secret = client.auth.vaults["test"]["key"]
    
    # Test health
    response = client.auth.client.get('/test/health')
    print(response.json())

# One-shot factory
from tests.flask_test import create_test_client
client = create_test_client()
```

### Storage Backends

- **Tables**: SQLite (`:memory:`)
- **Documents**: Python dicts
- **Config**: `STORAGE_MODE=1`

### Advanced: Manual Setup

```python
from campus.common import env
env.STORAGE_MODE = "1"

from tests.flask_test import FlaskTestClient, configure_for_testing
from campus.common.devops import deploy
import campus.auth

auth_app = deploy.create_app(campus.auth)
configure_for_testing(auth_app)

with FlaskTestClient(auth_app) as client:
    response = client.get('/test/health')
    print(response.json())
```

### When to Use
- ✅ Unit testing
- ✅ Component testing
- ✅ Fast feedback
- ✅ CI/CD (fastest)
- ❌ Network testing
- ❌ Deployment config testing

## Test Suite Execution

For running organized test suites, use the centralized test runner:

```python
# Run all unit tests
python tests/run_tests.py unit

# Run all integration tests  
python tests/run_tests.py integration

# Run all tests
python tests/run_tests.py all

# Run unit tests for specific module
python tests/run_tests.py unit --module vault

# Run with verbose output
python tests/run_tests.py integration -v

# Run with timeout
python tests/run_tests.py unit --timeout 60
```

The test runner automatically discovers and executes tests in the appropriate directories:
- `tests/unit/` - Fast, isolated component tests
- `tests/integration/` - Multi-component interaction tests

### Available Test Modules

- **auth** - Authentication service (OAuth, sessions, credentials)
- **api** - API service (circles, email OTP)
- **yapper** - Logging framework
- **common** - Shared utilities
- **storage** - Data persistence

Example:
```bash
python tests/run_tests.py unit --module auth
python tests/run_tests.py integration --module api
```

## When to Use Each Strategy

| Phase | Strategy | Notes |
|-------|----------|-------|
| **Unit Testing** | Flask Test Client | Fastest |
| **Integration Testing** | Local Services | Currently broken |
| **Manual Testing** | Development Server | Railway |
| **Demo** | Development Server | Most realistic |

### Debugging

1. Flask Test Client - Fast iteration
2. Local Services - Service interactions (when fixed)
3. Development Server - Deployment/network issues

## Quick Reference

### Configuration

```python
from campus.common import env

env.ENV = 'testing'      # Local services
env.ENV = 'development'  # Railway
env.STORAGE_MODE = '1'   # Test storage

from tests.flask_test import configure_for_testing
configure_for_testing(app)
```

### Test Execution

```bash
# Test suites
python tests/run_tests.py unit
python tests/run_tests.py integration
```

### Manual Testing

```python
# Development Server
import campus_python
from campus.common import env
env.ENV = 'development'
campus = campus_python.Campus()

# Local Services (broken)
from tests.fixtures import services
with services.init() as manager:
    campus = campus_python.Campus()

# Flask Test Client
from tests.flask_test import create_test_client_from_manager
from tests.fixtures import services
with services.init() as manager:
    client = create_test_client_from_manager(manager)
```

### Best Practices

1. Use test runner: `python tests/run_tests.py`
2. Entry points:
   - Local services: `tests.fixtures.services.init()` (broken)
   - Flask: `tests.flask_test.create_test_client_from_manager()`
3. Use context managers for cleanup
4. Start with Flask test client (fastest)
5. Keep tests independent

### Service Dependencies

```
auth → yapper → api
```

- **Auth**: No dependencies, provides credentials
- **Yapper**: Requires auth credentials
- **API**: Requires auth + yapper

**Current Issue**: Local service testing broken after auth/api refactor.

---

*For more information about testing, see [CONTRIBUTING.md](CONTRIBUTING.md) and [development-guidelines.md](development-guidelines.md).*
