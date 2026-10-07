"""campus.common

This is a namespace module for common Campus functionality.

Deployment orchestration lives in campus.deploy (moved out of the former
campus.common.devops): common code gates on the environment via
campus.common.env without depending on deployment code.
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
