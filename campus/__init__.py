"""campus

Campus namespace package - contains all Campus ecosystem modules.
"""

# Namespace package marker
__path__ = __import__('pkgutil').extend_path(__path__, __name__)

# Re-export submodules for static type checker compatibility
from . import apps
from . import client
from . import common
from . import models
from . import services
from . import storage
from . import vault

__all__ = [
    'apps',
    'client', 
    'common',
    'models',
    'services',
    'storage',
    'vault',
]
