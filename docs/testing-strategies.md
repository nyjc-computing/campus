# Campus Testing Strategies

This document outlines the three primary testing strategies available in the Campus project. Each strategy serves different purposes and provides different levels of integration with real services.

## Table of Contents

- [Overview](#overview)
- [Strategy 1: Development Server Testing](#strategy-1-development-server-testing)
- [Strategy 2: Local Service Testing](#strategy-2-local-service-testing)
- [Strategy 3: Flask Test Client Testing](#strategy-3-flask-test-client-testing)
- [When to Use Each Strategy](#when-to-use-each-strategy)
- [Quick Reference](#quick-reference)

## Overview

Campus provides three distinct testing strategies to accommodate different testing needs:

| Strategy | Environment | Data | Network | Use Case |
|----------|-------------|------|---------|----------|
| **Development Server** | Remote (Railway) | Simulated real data | Real HTTP | Manual testing, demos |
| **Local Services** | Local background processes | Test data | Real HTTP | Integration testing |
| **Flask Test Client** | In-process Flask apps | Test data | No network | Unit/component testing |

All strategies use the same Campus client interface, ensuring consistent testing patterns across different levels of integration.

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
os.environ['ENV'] = 'development'

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
from tests.fixtures import services

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

NOTE: Not fully working yet, WIP

**Purpose**: Test Campus clients with in-process Flask applications (no network calls).

### Environment
- **Services**: Flask app instances (not running servers)
- **Data**: Test data in-memory or test databases
- **Network**: No network - direct Flask test client calls
- **Speed**: Fastest option

### Usage

```python
from tests import flask_test
from tests.fixtures import services

# Create Campus client with Flask test adapters
with services.init() as manager:
    client = flask_test.create_test_client_from_manager(manager)
    
    # All operations use Flask test client internally
    vault = client.vault["test-vault"]  
    vault.set("key", "value")  # No HTTP - direct Flask calls
```

### Direct Flask App Testing

```python
from tests.flask_test import FlaskTestClient
from campus.common.devops import deploy
import campus.vault

# Create Flask app manually
vault_app = deploy.create_app(campus.vault)

# Wrap with our adapter
test_client = FlaskTestClient(vault_app)

# Use as JsonClient
response = test_client.get('/api/v1/vault/')
print(response.status_code)  # 401 (authentication required)
print(response.json())       # Error details
```

### When to Use
- ✅ Unit testing of client logic
- ✅ Component testing
- ✅ Fast test feedback loops
- ✅ Testing error handling
- ✅ CI/CD (fastest option)
- ❌ Testing actual network behavior
- ❌ Testing service deployment configurations

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

### Import Patterns

```python
# Development Server
from campus.client import Campus
client = Campus()  # Uses ENV variable

# Local Services  
from tests.fixtures import services
with services.init() as manager:
    client = Campus()  # Connects to local services

# Flask Test Client
from tests.flask_test import create_test_client_from_manager
from tests.fixtures import services
with services.init() as manager:
    client = create_test_client_from_manager(manager)
```

### Configuration

```python
# Set testing environment
import os
os.environ['ENV'] = 'testing'    # Local services
os.environ['ENV'] = 'development'  # Remote development server

# Test configuration for Flask apps
from tests.flask_test import configure_for_testing
configure_for_testing(app)  # Sets DEBUG=True, TESTING=True, adds health routes
```

### Service Dependencies

**Critical**: Services must be initialized in dependency order:

```
vault → yapper → apps
```

- **Vault**: No dependencies, provides authentication
- **Yapper**: Requires vault credentials for database access  
- **Apps**: Imports yapper routes, needs yapper fully initialized

**Note**: Current limitation - Apps service may fail during testing due to yapper → vault connection requirements during import. This is expected behavior and indicates architectural improvements needed in the yapper module for lazy loading.

### Best Practices

1. **Use context managers** for automatic cleanup
2. **Start with Flask test client** for new features
3. **Test error paths** with all strategies
4. **Keep tests independent** - don't rely on test order
5. **Use appropriate strategy** for the testing goal

---

*For more information about testing, see [CONTRIBUTING.md](CONTRIBUTING.md) and [development-guidelines.md](development-guidelines.md).*
