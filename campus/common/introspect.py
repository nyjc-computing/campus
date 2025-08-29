"""campus.common.introspect

Introspection utilities for the campus.common package.
"""
import inspect
import sys
from types import ModuleType


def get_caller_module() -> ModuleType:
    """Get the module of the target caller.

    *Note*: The module that calls get_caller_module() is the target. The caller is the module that called the target.
    """
    frame = inspect.currentframe()
    assert frame is not None
    assert frame.f_back is not None
    assert frame.f_back.f_back is not None
    try:
        # frame 0: get_caller_module, frame 1: target, frame 2: caller
        caller_frame = frame.f_back.f_back
        module_name = caller_frame.f_globals.get('__name__')
        assert isinstance(module_name, str)
        return sys.modules[module_name]
    finally:
        del frame
