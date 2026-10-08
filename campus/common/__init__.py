"""campus.common

This is a namespace module for common Campus functionality.

Deployment orchestration lives in campus.deploy (moved out of the former
campus.common.devops): common code gates on the environment via
campus.common.env without depending on deployment code.

The whole namespace imports without flask/werkzeug (#861). Submodules
that need them must import lazily at call time — see the module
docstrings in utils/url.py and errors/handlers.py BEFORE "tidying" any
import up to module level, and follow the same pattern for new code.
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
    http,
    introspect,
    schema,
    utils,
    validation,
)
