"""campus

Campus namespace package - contains all Campus ecosystem modules.
"""

# Namespace package marker
__path__ = __import__('pkgutil').extend_path(__path__, __name__)

# Note: Submodules are available via attribute access (campus.auth,
# campus.api, etc.) but are not imported by default to avoid init
# dependencies.
