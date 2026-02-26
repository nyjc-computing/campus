#!/usr/bin/env python3
"""Tests for field metadata validation in SQL schema generation.

These tests verify that invalid field metadata is caught during schema
generation, preventing silent errors from typos or incorrect types.
"""

import unittest
import dataclasses
from dataclasses import dataclass

from campus.model.base import InternalModel, Model
from campus.model import constraints


@dataclass
class TestModelWithStorage(Model):
    """Test model with storage field."""
    name: str = dataclasses.field(metadata={"storage": True})


@dataclass
class TestModelWithBadStorageBool(Model):
    """Test model with invalid storage metadata (non-bool)."""
    name: str = dataclasses.field(metadata={"storage": "yes"})


@dataclass
class TestModelWithBadStorageString(Model):
    """Test model with invalid storage metadata (string)."""
    name: str = dataclasses.field(metadata={"storage": "no"})


@dataclass
class TestModelWithBadConstraintsString(Model):
    """Test model with invalid constraints metadata (string instead of list)."""
    name: str = dataclasses.field(metadata={"constraints": "unique"})


@dataclass
class TestModelWithBadConstraintTypo(Model):
    """Test model with invalid constraint name (typo)."""
    name: str = dataclasses.field(metadata={"constraints": ["uniqe"]})


@dataclass
class TestModelWithBadConstraintType(Model):
    """Test model with invalid constraint type (int)."""
    name: str = dataclasses.field(metadata={"constraints": [123]})


@dataclass
class TestModelWithValidConstraints(Model):
    """Test model with valid constraints."""
    name: str = dataclasses.field(metadata={"constraints": [constraints.UNIQUE]})
    email: str = dataclasses.field(metadata={"constraints": ("unique",)})


@dataclass
class TestInternalModel(InternalModel):
    """Test InternalModel for validation."""
    name: str = dataclasses.field()


@dataclass
class TestInternalModelWithBadMetadata(InternalModel):
    """Test InternalModel with invalid metadata."""
    name: str = dataclasses.field(metadata={"storage": 1})


class TestFieldMetadataValidation(unittest.TestCase):
    """Test field metadata validation in SQL schema generation."""

    def test_valid_field_metadata(self):
        """Test that valid field metadata passes validation."""
        # Lazy import as per AGENTS.md guidelines
        from campus.storage.tables.backend import postgres
        from campus.storage.tables.backend import sqlite

        # Valid: storage=True (default)
        field = TestModelWithStorage.fields()["name"]
        postgres._validate_field_metadata(field)  # Should not raise
        sqlite._validate_field_metadata(field)  # Should not raise

        # Valid: storage=False
        field = dataclasses.field(metadata={"storage": False})
        postgres._validate_field_metadata(field)  # Should not raise

        # Valid: constraints=["unique"]
        field = TestModelWithValidConstraints.fields()["name"]
        postgres._validate_field_metadata(field)  # Should not raise

        # Valid: constraints=("unique",)
        field = TestModelWithValidConstraints.fields()["email"]
        postgres._validate_field_metadata(field)  # Should not raise

    def test_invalid_storage_metadata_string(self):
        """Test that non-bool storage metadata raises TypeError."""
        from campus.storage.tables.backend import postgres

        field = TestModelWithBadStorageString.fields()["name"]
        with self.assertRaisesRegex(TypeError, "metadata 'storage' must be bool"):
            postgres._validate_field_metadata(field)

    def test_invalid_storage_metadata_truthy_string(self):
        """Test that truthy string for storage raises TypeError."""
        from campus.storage.tables.backend import postgres

        field = TestModelWithBadStorageBool.fields()["name"]
        with self.assertRaisesRegex(TypeError, "metadata 'storage' must be bool"):
            postgres._validate_field_metadata(field)

    def test_invalid_storage_metadata_int(self):
        """Test that integer for storage raises TypeError."""
        from campus.storage.tables.backend import postgres

        field = TestInternalModelWithBadMetadata.fields()["name"]
        with self.assertRaisesRegex(TypeError, "metadata 'storage' must be bool"):
            postgres._validate_field_metadata(field)

    def test_invalid_constraints_metadata_string(self):
        """Test that string for constraints raises TypeError."""
        from campus.storage.tables.backend import postgres

        field = TestModelWithBadConstraintsString.fields()["name"]
        with self.assertRaisesRegex(TypeError, "metadata 'constraints' must be list or tuple"):
            postgres._validate_field_metadata(field)

    def test_invalid_constraint_typo(self):
        """Test that typo in constraint name raises ValueError."""
        from campus.storage.tables.backend import postgres, sqlite

        field = TestModelWithBadConstraintTypo.fields()["name"]
        with self.assertRaisesRegex(ValueError, "invalid constraint 'uniqe'"):
            postgres._validate_field_metadata(field)

        # SQLite backend should have same validation
        with self.assertRaisesRegex(ValueError, "invalid constraint 'uniqe'"):
            sqlite._validate_field_metadata(field)

    def test_invalid_constraint_type(self):
        """Test that non-string constraint raises TypeError."""
        from campus.storage.tables.backend import postgres

        field = TestModelWithBadConstraintType.fields()["name"]
        with self.assertRaisesRegex(TypeError, "constraint at index 0 must be str"):
            postgres._validate_field_metadata(field)

    def test_internal_model_validation(self):
        """Test that InternalModel fields are also validated."""
        from campus.storage.tables.backend import postgres

        field = TestInternalModel.fields()["name"]
        postgres._validate_field_metadata(field)  # Should not raise

        field = TestInternalModelWithBadMetadata.fields()["name"]
        with self.assertRaisesRegex(TypeError, "metadata 'storage' must be bool"):
            postgres._validate_field_metadata(field)


if __name__ == "__main__":
    unittest.main()

