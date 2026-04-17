"""Unit tests for Model base class serialization/deserialization."""

import dataclasses
import unittest

from campus.model.base import Model
from campus.common import schema


@dataclasses.dataclass(kw_only=True)
class TestModel(Model):
    """Test model with various field types for testing from_storage/to_storage."""
    id: str
    required_field: str = dataclasses.field(metadata={"mutable": False})
    optional_field: str | None = None
    optional_with_default: str = "default_value"
    list_field: list[str] = dataclasses.field(default_factory=list)
    dict_field: dict[str, str] = dataclasses.field(default_factory=dict)


class TestModelFromStorage(unittest.TestCase):
    """Tests for Model.from_storage() method."""

    def test_from_storage_with_all_fields(self):
        """from_storage should work when all fields are present in record."""
        record = {
            "id": "test123",
            "created_at": "2025-01-01T00:00:00Z",
            "required_field": "required",
            "optional_field": "optional",
            "optional_with_default": "custom",
            "list_field": ["a", "b"],
            "dict_field": {"key": "value"},
        }
        model = TestModel.from_storage(record)

        self.assertEqual(model.id, "test123")
        self.assertEqual(model.required_field, "required")
        self.assertEqual(model.optional_field, "optional")
        self.assertEqual(model.optional_with_default, "custom")
        self.assertEqual(model.list_field, ["a", "b"])
        self.assertEqual(model.dict_field, {"key": "value"})

    def test_from_storage_with_missing_optional_field(self):
        """from_storage should use None for missing optional fields."""
        record = {
            "id": "test123",
            "created_at": "2025-01-01T00:00:00Z",
            "required_field": "required",
            # optional_field is missing
            "optional_with_default": "custom",
        }
        model = TestModel.from_storage(record)

        self.assertEqual(model.optional_field, None)
        self.assertEqual(model.optional_with_default, "custom")

    def test_from_storage_with_missing_default_field(self):
        """from_storage should use field default when key is missing."""
        record = {
            "id": "test123",
            "created_at": "2025-01-01T00:00:00Z",
            "required_field": "required",
            # optional_with_default is missing - should use "default_value"
            # optional_field is missing - should use None
        }
        model = TestModel.from_storage(record)

        self.assertEqual(model.optional_with_default, "default_value")
        self.assertEqual(model.optional_field, None)

    def test_from_storage_with_missing_default_factory_field(self):
        """from_storage should use default_factory when key is missing."""
        record = {
            "id": "test123",
            "created_at": "2025-01-01T00:00:00Z",
            "required_field": "required",
        }
        model = TestModel.from_storage(record)

        self.assertEqual(model.list_field, [])
        self.assertEqual(model.dict_field, {})

    def test_from_storage_with_missing_required_field(self):
        """from_storage should raise KeyError with helpful message for required fields."""
        record = {
            "id": "test123",
            "created_at": "2025-01-01T00:00:00Z",
            # required_field is missing
        }
        with self.assertRaises(KeyError) as cm:
            TestModel.from_storage(record)

        error_msg = str(cm.exception)
        self.assertIn("required_field", error_msg)
        self.assertIn("TestModel", error_msg)
        self.assertIn("not found in storage record", error_msg)

    def test_from_storage_respects_storage_metadata_false(self):
        """from_storage should skip fields with storage=False metadata."""
        # Create a model instance and convert to storage
        model = TestModel(
            id="test123",
            required_field="required"
        )
        storage = model.to_storage()

        # Verify that only storage=True fields are included
        self.assertIn("id", storage)
        self.assertIn("required_field", storage)
        self.assertIn("created_at", storage)

        # Can load it back
        loaded = TestModel.from_storage(storage)
        self.assertEqual(loaded.id, "test123")
        self.assertEqual(loaded.required_field, "required")


class TestModelToStorage(unittest.TestCase):
    """Tests for Model.to_storage() method."""

    def test_to_storage_includes_all_storage_fields(self):
        """to_storage should include all fields with storage=True metadata."""
        model = TestModel(
            id="test123",
            required_field="required",
            optional_field="optional",
            optional_with_default="custom",
            list_field=["a", "b"],
            dict_field={"key": "value"},
        )
        storage = model.to_storage()

        self.assertEqual(storage["id"], "test123")
        self.assertEqual(storage["required_field"], "required")
        self.assertEqual(storage["optional_field"], "optional")
        self.assertEqual(storage["optional_with_default"], "custom")
        self.assertEqual(storage["list_field"], ["a", "b"])
        self.assertEqual(storage["dict_field"], {"key": "value"})

    def test_to_storage_serializes_datetime(self):
        """to_storage should serialize DateTime fields to strings."""
        model = TestModel(
            id="test123",
            required_field="required",
        )
        storage = model.to_storage()

        # created_at should be a string (from schema.DateTime)
        self.assertIsInstance(storage["created_at"], str)


class TestModelToResource(unittest.TestCase):
    """Tests for Model.to_resource() method."""

    def test_to_resource_includes_all_resource_fields(self):
        """to_resource should include all fields with resource=True metadata."""
        model = TestModel(
            id="test123",
            required_field="required",
            optional_field="optional",
        )
        resource = model.to_resource()

        self.assertEqual(resource["id"], "test123")
        self.assertEqual(resource["required_field"], "required")
        self.assertEqual(resource["optional_field"], "optional")

    def test_to_resource_roundtrip(self):
        """Model should be able to roundtrip through to_resource/from_resource."""
        original = TestModel(
            id="test123",
            required_field="required",
            optional_field="optional",
        )

        resource = original.to_resource()
        loaded = TestModel.from_resource(resource)

        self.assertEqual(loaded.id, original.id)
        self.assertEqual(loaded.required_field, original.required_field)
        self.assertEqual(loaded.optional_field, original.optional_field)


class TestModelRoundtrip(unittest.TestCase):
    """Tests for full roundtrip serialization/deserialization."""

    def test_to_storage_then_from_storage(self):
        """Model should survive to_storage -> from_storage roundtrip."""
        original = TestModel(
            id="test123",
            required_field="required",
            optional_field=None,  # explicitly None
            optional_with_default="custom",
            list_field=["a", "b"],
        )

        # First, save to storage (sparse - won't include None values from to_storage)
        storage = original.to_storage()

        # Load back from storage
        loaded = TestModel.from_storage(storage)

        self.assertEqual(loaded.id, original.id)
        self.assertEqual(loaded.required_field, original.required_field)
        self.assertEqual(loaded.optional_field, original.optional_field)
        self.assertEqual(loaded.optional_with_default, original.optional_with_default)
        self.assertEqual(loaded.list_field, original.list_field)

    def test_from_storage_sparse_record(self):
        """from_storage should handle sparse records (missing optional fields)."""
        # Simulate a sparse MongoDB document (optional fields not stored)
        sparse_record = {
            "id": "test123",
            "created_at": "2025-01-01T00:00:00Z",
            "required_field": "required",
        }

        model = TestModel.from_storage(sparse_record)

        self.assertEqual(model.id, "test123")
        self.assertEqual(model.required_field, "required")
        self.assertIsNone(model.optional_field)
        self.assertEqual(model.optional_with_default, "default_value")
        self.assertEqual(model.list_field, [])
        self.assertEqual(model.dict_field, {})


if __name__ == '__main__':
    unittest.main()
