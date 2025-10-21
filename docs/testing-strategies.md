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

Campus provides three distinct testing strategies to accommodate different testing needs:

| Strategy | Environment | Data | Network | Use Case |
|----------|-------------|------|---------|----------|
| **Development Server** | Remote (Railway) | Simulated real data | Real HTTP | Manual testing, demos |
| **Local Services** | Local background processes | Test data | Real HTTP | Integration testing |
| **Flask Test Client** | In-process Flask apps | Test data | No network | Unit/component testing |

All strategies use the same Campus client interface, ensuring consistent testing patterns across different levels of integration.

## Recommended Entry Points

For quick reference, here are the main entry points for each strategy:

- **Local Services**: `tests.fixtures.services.init()` - Sets up local HTTP services
- **Flask Test Client**: `tests.flask_test.create_test_client_from_manager()` - Creates Campus client with Flask test clients  
- **Development Server**: Set `ENV=development` and use `Campus()` - Connects to Railway

## Strategy 1: Development Server Testing

**Purpose**: Test against live development services with simulated real data.

### Environment
- **Vault**: `https://campusvault-development.up.railway.app/api/v1/`
- **Apps**: `https://campusapps-development.up.railway.app/api/v1/`
- **Data**: Simulated realistic data (different from production)
- **Network**: Real HTTP requests over the internet

### Usage

```python
import os
from campus.client import Campus

# Set environment to development
env.ENV = 'development'

# Client automatically uses development servers
client = Campus()

# Use normally - all requests go to Railway development services
vault = client.vault["my-vault"]
vault.set("api_key", "test-value")
```

### When to Use
- ✅ Manual testing and verification
- ✅ Demos and showcases  
- ✅ Testing with realistic data patterns
- ✅ Verifying deployment configurations
- ❌ Automated CI/CD (requires internet)
- ❌ Unit tests (too slow, external dependencies)

## Strategy 2: Local Service Testing

**Purpose**: Run Campus services locally in background threads for integration testing.

### Environment
- **Services**: Local Flask applications running in background
- **Data**: Test databases (PostgreSQL, MongoDB)
- **Network**: Real HTTP requests to localhost
- **Cleanup**: Automatic service shutdown

### Setup

```python
from tests.fixtures import services, postgres, mongodb

# Purge databases for clean state (optional but recommended)
postgres.purge_database("vaultdb")
postgres.purge_database("storagedb") 
mongodb.purge_database("storagedb")

# Context manager automatically handles setup/cleanup
with services.init() as manager:
    # manager.vault_app and manager.apps_app are running
    
    # Create clients normally - they connect to local services
    client = Campus()
    
    # Test against local services
    vault = client.vault["test-vault"]
    vault.set("test_key", "test_value")
    
    # Services automatically cleaned up when context exits
```

### Service Management

The `ServiceManager` follows strict initialization order:
1. **Vault** → Creates test credentials
2. **Yapper** → Requires vault credentials
3. **Apps** → Requires vault + yapper

```python
# Manual service management (if needed)
manager = services.create_service_manager()
manager.setup()  # Start all services
# ... test code ...
manager.close()  # Clean shutdown
```

### When to Use
- ✅ Integration testing
- ✅ Testing service interactions
- ✅ End-to-end workflows
- ✅ CI/CD automated testing
- ❌ Unit tests (too heavy)
- ❌ Performance testing (overhead from background services)

## Strategy 3: Flask Test Client Testing

**Purpose**: Test Campus clients with in-process Flask applications (no network calls).

### Environment
- **Services**: Flask app instances (not running servers)
- **Data**: In-memory SQLite and Python dictionaries 
- **Network**: No network - direct Flask test client calls
- **Speed**: Fastest option

### Setup

Use the factory functions for easy Flask test client creation:

```python
# Recommended: Use factory function with automatic cleanup
from tests.flask_test import create_test_client_from_manager
from tests.fixtures import services

with services.init() as manager:
    # Create Campus client with Flask test clients (no network calls)
    client = create_test_client_from_manager(manager)
    
    # Use like normal Campus client
    vault = client.vault["test-vault"]
    vault.set("test_key", "test_value")
    
    # Test health endpoints
    response = client.vault.client.get('/test/health')
    print(response.json())  # {'status': 'healthy', 'storage_mode': 'test'}

# Alternative: One-shot factory (less control over cleanup)
from tests.flask_test import create_test_client

client = create_test_client()
# Use client for testing (cleanup is automatic but less predictable)
```

### Storage Backends

Test storage uses lightweight, in-memory backends:

- **Tables**: SQLite in-memory database (`:memory:`)
- **Documents**: Python dictionaries 
- **Configuration**: `STORAGE_MODE=1` (any non-zero enables test mode)

### Advanced: Manual Setup

For advanced use cases where you need direct control over Flask apps:

```python
import os
env.STORAGE_MODE = "1"  # Enable test storage backends

from tests.flask_test import FlaskTestClient, configure_for_testing
from campus.common.devops.deploy import create_app
import campus.vault

# Create and configure Flask app manually
vault_app = create_app(campus.vault)
configure_for_testing(vault_app)  # Sets up test storage + health endpoints

# Use FlaskTestClient directly
with FlaskTestClient(vault_app) as client:
    response = client.get('/test/health')
    print(response.json())  # {'status': 'healthy', 'storage_mode': 'test'}
```
- **Documents**: Python dictionaries 
- **Configuration**: `STORAGE_MODE=1` (any non-zero enables test mode)

### When to Use
- ✅ Unit testing of client logic
- ✅ Component testing
- ✅ Fast test feedback loops
- ✅ Testing error handling
- ✅ CI/CD (fastest option)
- ❌ Testing actual network behavior
- ❌ Testing service deployment configurations

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

The test runner supports testing specific modules:
- **apps** - Campus apps service (API, authentication, OAuth)
- **vault** - Vault service (secrets management, access control)
- **yapper** - Yapper service (data processing, message handling)
- **common** - Common utilities (HTTP, validation, errors)
- **client** - Campus client library (API wrappers, interfaces)

Example:
```bash
python tests/run_tests.py unit --module vault    # Only vault unit tests
python tests/run_tests.py integration --module apps  # Only apps integration tests
```

## When to Use Each Strategy

### Development Workflow

| Phase | Strategy | Rationale |
|-------|----------|-----------|
| **Unit Testing** | Flask Test Client | Fastest feedback, no external dependencies |
| **Integration Testing** | Local Services | Test service interactions, realistic but controlled |
| **Manual Testing** | Development Server | Test with realistic data and deployment config |
| **Demo/Showcase** | Development Server | Most realistic user experience |

### Error Debugging

1. **Start with Flask Test Client** - Fast iteration, direct debugging
2. **Move to Local Services** - If you need service interactions
3. **Use Development Server** - If you suspect deployment/network issues

## Quick Reference

### Configuration

```python
# Set testing environment
import os
env.ENV = 'testing'      # Local services
env.ENV = 'development'  # Remote development server
env.STORAGE_MODE = '1'   # Enable test storage backends

# Test configuration for Flask apps
from tests.flask_test import configure_for_testing
configure_for_testing(app)  # Sets DEBUG=True, TESTING=True, adds health routes
```

### Test Execution

**For test suites**: Use the centralized test runner
```bash
python tests/run_tests.py unit
python tests/run_tests.py integration
```

**For manual testing/debugging**: Use these entry points for each strategy

```python
# Development Server
from campus.client import Campus
import os
env.ENV = 'development'
client = Campus()  # Uses ENV variable to connect to Railway

# Local Services (HTTP to localhost)
from tests.fixtures import services
with services.init() as manager:
    client = Campus()  # Connects to local HTTP services

# Flask Test Client (no network)
from tests.flask_test import create_test_client_from_manager
from tests.fixtures import services
with services.init() as manager:
    client = create_test_client_from_manager(manager)  # Uses Flask test clients
```

### Best Practices

1. **Use the test runner** for organized test execution (`python tests/run_tests.py`)
2. **Use proper entry points**:
   - Local services: `tests.fixtures.services.init()` 
   - Flask test clients: `tests.flask_test.create_test_client_from_manager()`
3. **Use context managers** for automatic cleanup in manual testing
4. **Start with Flask test client** for new features (fastest feedback)
5. **Test error paths** with all strategies
6. **Keep tests independent** - don't rely on test order
7. **Use appropriate strategy** for the testing goal

### Architecture Notes

**Service Dependencies**: Services must be initialized in dependency order:
```
vault → yapper → apps
```

- **Vault**: No dependencies, provides authentication
- **Yapper**: Requires vault credentials for database access  
- **Apps**: Imports yapper routes, needs yapper fully initialized

**Current Limitation**: Apps service may fail during testing due to yapper → vault connection requirements during import. This indicates architectural improvements needed in the yapper module for lazy loading.

---

*For more information about testing, see [CONTRIBUTING.md](CONTRIBUTING.md) and [development-guidelines.md](development-guidelines.md).*
