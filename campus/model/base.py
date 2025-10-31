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


@dataclass(frozen=True)
class Model(typing.Protocol):
    """Base class for all models in Campus."""
    id: schema.CampusID | schema.UserID
    created_at: schema.DateTime

    @classmethod
    def fields(cls) -> dict[str, dataclasses.Field]:
        return {field.name: field for field in dataclasses.fields(cls)}

    @classmethod
    def from_resource(cls, resource: dict[str, typing.Any]) -> "Model":
        """Create a model instance from a resource dictionary."""
        return cls(
            **{
                field.name: resource[field.name]
                for field in cls.fields().values()
                if field.metadata.get("resource", True)
            }
        )

    @classmethod
    def from_storage(cls, record: dict[str, typing.Any]) -> "Model":
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
