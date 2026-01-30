"""Import verification tests for campus.model module.

These tests verify that all declared exports are actually available and importable.
This catches module export consistency bugs where code assumes something is available
from a module but it's not actually exported in __all__.
"""

import inspect
import unittest


class TestModelExports(unittest.TestCase):
    """Test that campus.model exports are consistent and importable."""

    def test_model_exports_all_exist(self):
        """Verify all items in campus.model.__all__ are actually available.

        This catches bugs where:
        - An item is listed in __all__ but not imported
        - An item is listed in __all__ but the import failed
        - An item is listed in __all__ but is a module/submodule

        This is a general test for module export consistency, not specific
        to any particular model.
        """
        import campus.model

        for name in campus.model.__all__:
            # Verify the attribute exists
            self.assertTrue(
                hasattr(campus.model, name),
                f"{name} is in __all__ but not available as an attribute"
            )

            # Verify it's actually a class/dataclass/function, not a module
            attr = getattr(campus.model, name)
            is_callable = (
                inspect.isclass(attr) or
                inspect.isfunction(attr) or
                callable(attr)
            )
            self.assertTrue(
                is_callable,
                f"{name} is exported but not a class/function/callable (got {type(attr).__name__})"
            )

    def test_model_submodules_importable(self):
        """Verify all model submodules can be imported without errors.

        This catches import-time errors in model submodules that might
        not be caught by the exports test (e.g., if a submodule has
        side effects at import time).
        """
        import campus.model

        # Test that key model submodules can be imported
        submodules = [
            "campus.model.base",
            "campus.model.assignment",
            "campus.model.circle",
            "campus.model.submission",
            "campus.model.user",
            "campus.model.credentials",
        ]

        for submodule_name in submodules:
            try:
                __import__(submodule_name)
            except ImportError as e:
                self.fail(f"Failed to import {submodule_name}: {e}")
            except Exception as e:
                self.fail(f"Unexpected error importing {submodule_name}: {e}")

    def test_api_resource_modules_importable(self):
        """Verify all API resource modules can be imported without errors.

        This catches import errors in API resource modules, which typically
        depend on campus.model exports. If a model is not exported properly,
        the corresponding resource module will fail to import.

        This is the deployment smoke test that would have caught the
        missing Submission/Response/Feedback exports.
        """
        resource_modules = [
            "campus.api.resources.submission",
            "campus.api.resources.assignment",
            "campus.api.resources.credentials",
            "campus.api.resources.circles",
            "campus.api.resources.emailotp",
        ]

        for module_name in resource_modules:
            try:
                __import__(module_name)
            except AttributeError as e:
                self.fail(f"Failed to import {module_name} due to AttributeError: {e}")
            except ImportError as e:
                self.fail(f"Failed to import {module_name}: {e}")
            except Exception as e:
                self.fail(f"Unexpected error importing {module_name}: {e}")


if __name__ == '__main__':
    unittest.main()
