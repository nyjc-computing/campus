"""campus.common

This is a namespace module for common Campus functionality.

Deployment orchestration lives in campus.deploy (moved out of the former
campus.common.devops): common code gates on the environment via
campus.common.env without depending on deployment code.

The whole namespace imports without flask/werkzeug (#861) or requests
(#967). Submodules that need them must import lazily at call time — see
the module docstrings in utils/url.py and errors/handlers.py BEFORE
"tidying" any import up to module level, and follow the same pattern for
new code.

The former campus.common.http client moved to campus.audit.http (#970):
its only consumers were the audit service's client and the cross-service
test harness, making it audit domain rather than shared infrastructure.
"""

__all__ = [
    "env",
    "errors",
    "introspect",
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
