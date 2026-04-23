"""campus.common.schema.openapi

OpenAPI schema definitions for Campus.

These schema follow OpenAPI 3 for easy generation of API documentation.
These datatype classes also subclass the most appropriate Python type,
for easy compatibility with schema validation.
- __str__() returns a JSON string representation of the value

See: https://swagger.io/specification/v3/#data-types
"""

from typing import Any, Self, Type
from urllib import parse

from campus.common.utils import utc_time


class BooleanMeta(type):
    """Required to override isinstance() checks for Boolean."""
    def __instancecheck__(cls, instance: Any) -> bool:
        return isinstance(instance, (Boolean, bool))


class Boolean(int, metaclass=BooleanMeta):
    """Emulates Python bool behavior.

    Python bool is marked as final and cannot be subclassed. Thus,
    Boolean emulates bool behavior.
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
        raise (
            TypeError(f"__eq__ not implemented for {type(other)}")
        ) from None

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass


class Integer(int):
    """Emulates Python int behavior."""

    def __new__(cls, value: int):
        return super().__new__(cls, value)

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        """Raise a Type error if value is not a valid int.

        Arguments:
        - value: Any
            The value to validate

        Raises:
            TypeError if value is not an int
        """
        pass


class Number(float):
    """Emulates Python float behavior."""

    def __new__(cls, value: float):
        return super().__new__(cls, value)

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        """Raises a TypeError if value is not a float.

        Arguments:
        - value: Any
            The value to validate

        Raises:
            TypeError if value is not a float
        """
        pass


class String(str):
    """Emulates Python str behavior."""

    def __new__(cls, value: str):
        if value in (None,):
            raise ValueError(
                f"{cls.__name__} cannot be initialized with {value}"
            ) from None
        return super().__new__(cls, value)

    def __str__(self) -> str:
        return super().__str__()

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass


class Date(String):
    """Emulates Python datetime.date behavior.

    Since date-time is considered a string format in OpenAPI 3, for
    future compatibility we have Date subclass str.
    This class 
    """

    def __new__(cls, value: str):
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"DateTime({self})"

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass

    @classmethod
    def from_date(cls: Type[Self], d: utc_time.date) -> Self:
        """Create a Date string from a UTC date object."""
        return cls(utc_time.to_rfc3339(d))

    @classmethod
    def utcafter(cls: Type[Self], today: Self | None = None, **delta) -> Self:
        """Get a Date string at a given delta after the current time.

        Keyword arguments:
        - **delta: follows that of timedelta
        """

        _t = utc_time.today() if today is None else today.to_date()
        assert isinstance(_t, utc_time.date), f"Expected date, got {_t}"
        return cls.from_date(utc_time.after(_t, **delta)) # pyright: ignore[reportArgumentType]

    @classmethod
    def today(cls: Type[Self]) -> Self:
        """Get the current UTC time as a DateTime string."""
        return cls.from_date(utc_time.today())

    def to_date(self) -> utc_time.date:
        """Convert the DateTime string to a UTC date object."""
        return utc_time.from_rfc3339(self).date()

    @property
    def year(self) -> int:
        """Passthrough to datetime.year"""
        return self.to_date().year

    @property
    def month(self) -> int:
        """Passthrough to datetime.month"""
        return self.to_date().month

    @property
    def day(self) -> int:
        """Passthrough to datetime.day"""
        return self.to_date().day


class DateTime(String):
    """Emulates Python datetime.datetime behavior.

    Since date-time is considered a string format in OpenAPI 3, for
    future compatibility we have DateTime subclass str.
    However, we emulate the most common datetime operations required by
    Campus.
    """

    def __new__(cls, value: str):
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"DateTime({self})"

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass

    @classmethod
    def from_datetime(cls: Type[Self], dt: utc_time.datetime) -> Self:
        """Create a DateTime string from a UTC datetime object."""
        return cls(utc_time.to_rfc3339(dt))

    @classmethod
    def from_timestamp(cls: Type[Self], ts: int) -> Self:
        """Create a DateTime string from a UTC timestamp."""
        return cls.from_datetime(utc_time.from_timestamp(ts))

    @classmethod
    def utcafter(cls: Type[Self], now: Self | None = None, **delta) -> Self:
        """Get a DateTime string at a given delta after the current time.

        Keyword arguments:
        - **delta: follows that of timedelta
        """
        dtnow = utc_time.now() if now is None else now.to_datetime()
        assert isinstance(dtnow, utc_time.datetime), f"Expected datetime, got {dtnow}"
        return cls.from_datetime(utc_time.after(dtnow, **delta)) # pyright: ignore[reportArgumentType]

    @classmethod
    def utcnow(cls: Type[Self]) -> Self:
        """Get the current UTC time as a DateTime string."""
        return cls.from_datetime(utc_time.now())

    def to_datetime(self) -> utc_time.datetime:
        """Convert the DateTime string to a UTC datetime object."""
        return utc_time.from_rfc3339(self)

    def to_timestamp(self) -> int:
        """Convert the DateTime string to a UTC timestamp."""
        return utc_time.to_timestamp(self.to_datetime())

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


class Email(String):
    """Emulates Python str behavior for Emails."""

    def __new__(cls, value: str):
        return super().__new__(cls, str(value))

    def __repr__(self) -> str:
        return f"Email({self})"

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass

    @property
    def user(self) -> str:
        """Get the local part of the email (before the @)."""
        return str(self).split("@")[0]

    @property
    def domain(self) -> str:
        """Get the domain part of the email (after the @)."""
        return str(self).split("@")[1]


class Time(String):
    """HHMM (24-hr) representation of time, without seconds or
    microseconds.

    `time` is not a defined string format in OpenAPI 3, but `format` is
    an open value so we define time as a string format.
    """

    def __new__(cls, value: str):
        if (
                len(value) != 4
                or not value.isascii()
                or not value.isdecimal()
        ):
            raise ValueError(f"{value!r} is not a valid HHMM-format string")
        hh, mm = value[:2], value[2:]
        if int(hh) >= 24 or int(mm) >= 60:
            raise ValueError(f"{value!r} does not represent a HHMM time earlier than 2359")
        return super().__new__(cls, value)

    def __repr__(self) -> str:
        return f"Time('{self!s}')"

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass

    def to_time(self) -> utc_time.time:
        """Convert the DateTime string to a UTC date object."""
        return utc_time.time(hour=self.hour, minute=self.minute)

    @property
    def hour(self) -> int:
        """hour as an integer"""
        return int(self[:2])

    @property
    def minute(self) -> int:
        """minute as an integer"""
        return int(self[2:])


class Url(String):
    """Emulates Python str behavior for URLs."""

    def __new__(cls, value: str):
        return super().__new__(cls, str(value))

    def __repr__(self) -> str:
        return f"Url({super().__str__()})"

    def __str__(self) -> str:
        return super().__str__()

    @classmethod
    def raise_for_validation(cls, value: Any) -> None:
        # Add a docstring
        pass

    @property
    def scheme(self) -> str:
        """Get the URL scheme (e.g., "http", "https")."""
        return parse.urlparse(self).scheme

    @property
    def netloc(self) -> str:
        """Get the URL network location (e.g., "example.com:8080")."""
        return parse.urlparse(self).netloc

    @property
    def path(self) -> str:
        """Get the URL path (e.g., "/api/v1/resource")."""
        return parse.urlparse(self).path

    @property
    def query(self) -> str:
        """Get the URL query string (e.g., "key=value&foo=bar")."""
        return parse.urlparse(self).query

    @property
    def fragment(self) -> str:
        """Get the URL fragment (e.g., "section1")."""
        return parse.urlparse(self).fragment

    def get_query_params(self) -> dict[str, str]:
        """Get the URL query parameters as a dictionary."""
        return dict(parse.parse_qsl(self.query))
    
    @classmethod
    def unparse(
        cls: Type[Self],
        parts: tuple[str, str, str, str, str, str]
    ) -> Self:
        """Unparse the URL components into a URL string."""
        return cls(parse.urlunparse(parts))


class Array(list):
    pass


class Object(dict):
    pass
