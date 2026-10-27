"""campus.common

This is a namespace module for common Campus functionality.

Deployment orchestration lives in campus.deploy (moved out of the former
campus.common.devops): common code gates on the environment via
campus.common.env without depending on deployment code.

The whole namespace imports without flask/werkzeug (#861) or requests
(#967). Submodules that need them must import lazily at call time — see
the module docstrings in utils/url.py and errors/handlers.py BEFORE
"tidying" any import up to module level, and follow the same pattern for
new code. The http submodule is itself lazy (default.py imports requests
at module level): access it via "from campus.common import http",
resolved by module __getattr__, or import campus.common.http directly.
"""

__all__ = [
    "env",
    "errors",
    "introspect",
    "http",
    "schema",
    "utils",
    "validation",
]

from . import (
    env,
    errors,
    introspect,
    schema,
    utils,
    validation,
)


def __getattr__(name):
    # PEP 562: http pulls in requests (and, through utils.secret, bcrypt)
    # at import time, so it is resolved on demand instead of eagerly.
    # import_module, not "from . import http": a from-import consults
    # this same __getattr__ and recurses forever.
    if name == "http":
        import importlib
        return importlib.import_module(__name__ + ".http")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
