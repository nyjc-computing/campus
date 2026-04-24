"""campus

Campus namespace package - contains all Campus ecosystem modules.

This package serves as a unified namespace for all Campus services:
- campus.auth: Authentication and authorization service
- campus.api: Main API endpoints
- campus.audit: Audit and tracing service
- campus.common: Shared utilities and schemas
- campus.model: Data models
- campus.storage: Storage abstraction layer

Note: This is a namespace package using pkgutil.extend_path().
Submodules are not imported here to avoid circular dependencies.
They are discovered dynamically at runtime and should be explicitly
imported when needed (e.g., "from campus.auth import resources").
"""

# Namespace package marker - allows extending with campus-python package
__path__ = __import__('pkgutil').extend_path(__path__, __name__)
