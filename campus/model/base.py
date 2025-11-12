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
    This class is not used; the allowed arguments are documented here
    for reference.
    """
    # Whether the field is returned in API responses. Default is True.
    resource: bool
    # Whether the field is stored in the database. Default is True.
    storage: bool
    # Any additional constraints for the field, e.g., UNIQUE.
    constraints: typing.Sequence[str]


@dataclass(kw_only=True)
class Model(typing.Protocol):
    """Base class for all models in Campus."""
    id: schema.CampusID | schema.UserID
    created_at: schema.DateTime = dataclasses.field(
        default_factory=schema.DateTime.utcnow
    )

    @classmethod
    def fields(cls) -> dict[str, dataclasses.Field]:  # type: ignore[override]
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
        return cls(
            **{
                field.name: record[field.name]
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
