"""campus.common.schema.base

Base schema definitions, enums, and constants for Campus.
"""

from typing import Any, Literal

from campus.common.utils import utc_time

ResponseStatus = Literal["ok", "error"]


# TODO: Replace with OpenAPI-based pattern-string schema
CampusID = str
UserID = str


# Data types
# These data type classes subclass the most appropriate Python type, for easy
# compatibility with schema validation.
# __str__() returns a JSON string representation of the value
# See https://swagger.io/specification/v3/#data-types


class BooleanMeta(type):
    """Required to override isinstance() checks for Boolean."""
    def __instancecheck__(cls, instance: Any) -> bool:
        return isinstance(instance, (Boolean, bool))


class Boolean(int, metaclass=BooleanMeta):
    """Emulates Python bool behavior.

    Python bool is marked as final and cannot be subclassed. Thus, Boolean
    emulates bool behavior.
    """

    def __new__(cls, value: bool):
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"{bool(self)}"

    def __str__(self) -> str:
        return "true" if self else "false"

    def __bool__(self) -> bool:
        return True if self else False

    def __eq__(self, other: object) -> bool:
        match other:
            case Boolean():
                return True if bool(self) == bool(other) else False
            case bool():
                return True if bool(self) == other else False
        raise TypeError(f"__eq__ not implemented for {type(other)}")


class Integer(int):
    """Emulates Python int behavior."""

    def __new__(cls, value: int):
        return super().__new__(cls, value)


class Number(float):
    """Emulates Python float behavior."""

    def __new__(cls, value: float):
        return super().__new__(cls, value)


class String(str):
    """Emulates Python str behavior."""

    def __new__(cls, value: str):
        return super().__new__(cls, value)


class DateTime(String):
    """Emulates Python datetime behavior.

    Since date-time is considered a string format in OpenAPI 3, for future
    compatibility we have DateTime subclass str.
    However, we emulate the most common datetime operations required by Campus.
    """

    def __new__(cls, value: str):
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"DateTime({str(self)})"

    def __str__(self) -> str:
        return str(self)

    def to_datetime(self) -> utc_time.datetime:
        """Convert the DateTime string to a UTC datetime object."""
        return utc_time.from_rfc3339(self)
    
    @property
    def year(self) -> int:
        """Passthrough to datetime.year"""
        return self.to_datetime().year

    @property
    def month(self) -> int:
        """Passthrough to datetime.month"""
        return self.to_datetime().month

    @property
    def day(self) -> int:
        """Passthrough to datetime.day"""
        return self.to_datetime().day

    @property
    def hour(self) -> int:
        """Passthrough to datetime.hour"""
        return self.to_datetime().hour

    @property
    def minute(self) -> int:
        """Passthrough to datetime.minute"""
        return self.to_datetime().minute

    @property
    def second(self) -> int:
        """Passthrough to datetime.second"""
        return self.to_datetime().second


class Array(list):
    pass


class Object(dict):
    pass
