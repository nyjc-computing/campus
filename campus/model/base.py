"""campus.model.base

Base Model class.
"""

import dataclasses
from dataclasses import dataclass
import typing

from campus.common import schema


class FieldMeta(typing.TypedDict):
    """Metadata for a model field.

    These are passed to the metadata parameter of dataclasses.field().
    See https://docs.python.org/3/library/dataclasses.html#dataclasses.field

    Note: Types are enforced when generating SQL schemas via
    TableInterface.init_from_model(). Invalid metadata will raise
    TypeError or ValueError.

    Attributes:
        resource: Whether the field is returned in API responses. Default is True.
        storage: Whether the field is stored in the database. Must be bool. Default is True.
        constraints: List of constraint names. Must be list/tuple of str.
                     Valid constraint names are defined in campus.model.constraints
                     (e.g., "unique" for UNIQUE constraint).
    """
    # Whether the field is returned in API responses. Default is True.
    resource: bool
    # Whether the field is stored in the database. Must be bool. Default is True.
    storage: bool
    # Any additional constraints for the field. Must be list/tuple of str.
    # Valid values are defined in campus.model.constraints (e.g., "unique").
    constraints: typing.Sequence[str]


@dataclass(kw_only=True)
class InternalModel(typing.Protocol):
    """Base class for internal models in Campus.

    Internal models are not exposed through Campus API endpoints,
    but are used internally as intermediate representations.
    """

    @classmethod
    def fields(cls) -> dict[str, dataclasses.Field]:
        return {field.name: field for field in dataclasses.fields(cls)}

    @classmethod
    def validate_update(cls, update: dict[str, typing.Any]) -> None:
        """Validate an update dictionary against the model's mutable
        fields.

        Args:
            update: Dictionary of fields to update

        Raises:
            ValueError: If any field in the update is not mutable
        """
        if not update:
            raise ValueError("No fields provided for update validation")
        for field_name in update.keys():
            field = cls.fields().get(field_name)
            if field is None:
                raise ValueError(
                    f"Field '{field_name}' does not exist in model"
                )
            if not field.metadata.get("mutable", False):
                raise ValueError(f"Field '{field_name}' is not mutable")

    @classmethod
    def from_resource(
            cls: type[typing.Self],
            resource: dict[str, typing.Any]
    ) -> typing.Self:
        """Create a model instance from a resource dictionary."""
        return cls(
            **{
                field.name: resource[field.name]
                for field in cls.fields().values()
                if field.metadata.get("resource", True)
            }
        )

    @classmethod
    def from_storage(
            cls: type[typing.Self],
            record: dict[str, typing.Any]
    ) -> typing.Self:
        """Create a model instance from a storage record dictionary."""
        def get_value(f: dataclasses.Field) -> typing.Any:
            """Get value from record, falling back to field default if missing."""
            if f.name in record:
                return record[f.name]
            # Key not in record - use field default if available
            if f.default is not dataclasses.MISSING:
                return f.default
            if f.default_factory is not dataclasses.MISSING:  # type: ignore[attr-defined]
                return f.default_factory()  # type: ignore[attr-defined]
            # No default available - raise KeyError with clear message
            raise KeyError(
                f"Required field '{f.name}' not found in storage record "
                f"for model '{cls.__name__}'"
            )

        return cls(
            **{
                field.name: get_value(field)
                for field in cls.fields().values()
                if field.metadata.get("storage", True)
            }
        )

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert the model instance to a resource dictionary."""
        return {
            field.name: getattr(self, field.name)
            for field in self.fields().values()
            if field.metadata.get("resource", True)
        }

    def to_storage(self) -> dict[str, typing.Any]:
        """Convert the model instance to a storage record dictionary."""
        return {
            field.name: getattr(self, field.name)
            for field in self.fields().values()
            if field.metadata.get("storage", True)
        }


@dataclass(kw_only=True)
class Model(InternalModel):
    """Base class for all public models in Campus.
    
    Public models are queryable through Campus API endpoints,
    and may be returned by the Python API.
    """
    id: schema.CampusID | schema.UserID
    created_at: schema.DateTime = dataclasses.field(
        default_factory=schema.DateTime.utcnow
    )
