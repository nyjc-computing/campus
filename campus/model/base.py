"""campus.model.base

Base Model class.
"""

import dataclasses
import types
import typing
from dataclasses import dataclass

from campus.common import schema


def _coercible_str_type(hint: typing.Any) -> type | None:
    """Resolve the str subclass a type hint declares, if any.

    Handles plain annotations (schema.DateTime) and Optional unions
    (schema.DateTime | None): storage/resource round-trips keep no
    subclass, so Optional[schema.*] fields must coerce too (#847).
    Returns None for non-str hints (Model, list, bare unions of
    multiple non-None members, ...).
    """
    field_type = hint
    origin = typing.get_origin(field_type)
    # PEP 604 `X | None` unions have origin types.UnionType; subscripted
    # typing.Union has origin typing.Union. Both are Optional-style.
    if origin is typing.Union or origin is types.UnionType:
        members = [
            arg for arg in typing.get_args(field_type)
            if arg is not type(None)
        ]
        if len(members) != 1:
            return None
        field_type = members[0]
    if isinstance(field_type, type) and issubclass(field_type, str):
        return field_type
    return None


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
        for field_name in update:
            field = cls.fields().get(field_name)
            if field is None:
                raise ValueError(
                    f"Field '{field_name}' does not exist in model"
                )
            if not field.metadata.get("mutable", True):
                raise ValueError(f"Field '{field_name}' is not mutable")

    @classmethod
    def from_resource(
            cls: type[typing.Self],
            resource: dict[str, typing.Any]
    ) -> typing.Self:
        """Create a model instance from a resource dictionary.

        Fields declared init=False are assigned after construction,
        since they cannot be passed to __init__(). Values for
        Model-typed fields are deserialized recursively, and plain
        strings are coerced to annotated str subclasses
        (e.g. schema.DateTime).
        """
        try:
            hints = typing.get_type_hints(cls)
        except Exception:
            # Unresolvable type hints disable coercion below
            hints = {}

        init_kwargs: dict[str, typing.Any] = {}
        post_init_fields: dict[str, typing.Any] = {}
        for field in cls.fields().values():
            if not field.metadata.get("resource", True):
                continue
            if field.name not in resource:
                continue
            value = resource[field.name]
            field_type = hints.get(field.name)
            if (isinstance(value, dict) and isinstance(field_type, type)
                    and issubclass(field_type, Model)):
                value = field_type.from_resource(value)
            else:
                str_type = _coercible_str_type(field_type)
                if str_type is not None and isinstance(value, str) \
                        and not isinstance(value, str_type):
                    value = str_type(value)
            if field.init:
                init_kwargs[field.name] = value
            else:
                post_init_fields[field.name] = value

        instance = cls(**init_kwargs)
        for field_name, value in post_init_fields.items():
            setattr(instance, field_name, value)
        return instance

    @classmethod
    def from_storage(
            cls: type[typing.Self],
            record: dict[str, typing.Any]
    ) -> typing.Self:
        """Create a model instance from a storage record dictionary.

        Storage records carry plain strings (JSON/BSON); values for
        fields annotated as str subclasses (schema.DateTime, CampusID,
        Email, Url, ...) are coerced to the annotated type, mirroring
        from_resource(). Optional annotations (schema.DateTime | None)
        coerce too (#847) — storage round-trips keep no subclass.
        """
        try:
            hints = typing.get_type_hints(cls)
        except Exception:
            # Unresolvable type hints disable coercion below
            hints = {}

        def get_value(f: dataclasses.Field) -> typing.Any:
            """Get value from record, falling back to field default if missing."""
            if f.name in record:
                value = record[f.name]
            # Key not in record - use field default if available
            elif f.default is not dataclasses.MISSING:
                return f.default
            elif f.default_factory is not dataclasses.MISSING:  # type: ignore[attr-defined]
                return f.default_factory()  # type: ignore[attr-defined]
            # No default available - raise KeyError with clear message
            else:
                raise KeyError(
                    f"Required field '{f.name}' not found in storage record "
                    f"for model '{cls.__name__}'"
                )
            str_type = _coercible_str_type(hints.get(f.name))
            if str_type is not None and isinstance(value, str) \
                    and not isinstance(value, str_type):
                value = str_type(value)
            return value

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
