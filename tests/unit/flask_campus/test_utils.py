"""Unit tests for campus.flask_campus.utils argument unpacking.

Query and path parameters always arrive as strings; unpack_into must
coerce them to the handler's annotated scalar type and reject values
that do not convert.
"""

import unittest

from campus.common.errors import ValidationError
from campus.flask_campus import utils


def _handler(
        client_id: str,
        vault: str,
        permission: int,
        ratio: float = 1.0,
        flag: bool = False,
) -> dict:
    """Stub handler echoing back the arguments it received."""
    return {
        "client_id": client_id,
        "vault": vault,
        "permission": permission,
        "ratio": ratio,
        "flag": flag,
    }


def _kwargs_handler(permission: int, **rest: str) -> tuple[int, dict]:
    """Stub handler accepting extra arguments via **kwargs."""
    return permission, rest


class TestUnpackIntoCoercion(unittest.TestCase):
    """String request values must honor annotated int/float/bool types."""

    def test_int_annotated_string_is_coerced(self):
        result = utils.unpack_into(
            _handler,
            client_id="client_1", vault="test_vault", permission="1"
        )
        self.assertIsInstance(result["permission"], int)
        self.assertEqual(result["permission"], 1)

    def test_float_annotated_string_is_coerced(self):
        result = utils.unpack_into(
            _handler,
            client_id="client_1", vault="test_vault", permission="1",
            ratio="0.5"
        )
        self.assertEqual(result["ratio"], 0.5)

    def test_bool_annotated_string_is_coerced(self):
        result = utils.unpack_into(
            _handler,
            client_id="client_1", vault="test_vault", permission="1",
            flag="true"
        )
        self.assertIs(result["flag"], True)

    def test_bool_annotated_string_is_case_insensitive(self):
        result = utils.unpack_into(
            _handler,
            client_id="client_1", vault="test_vault", permission="1",
            flag="FALSE"
        )
        self.assertIs(result["flag"], False)

    def test_non_string_values_pass_through(self):
        result = utils.unpack_into(
            _handler,
            client_id="client_1", vault="test_vault", permission=1,
            ratio=0.5, flag=True
        )
        self.assertEqual(result["permission"], 1)
        self.assertIs(result["flag"], True)

    def test_str_annotation_left_untouched(self):
        result = utils.unpack_into(
            _handler,
            client_id="client_1", vault="007", permission="1"
        )
        self.assertEqual(result["vault"], "007")

    def test_uncoercible_int_raises_field_error(self):
        with self.assertRaises(ValidationError) as ctx:
            utils.unpack_into(
                _handler,
                client_id="client_1", vault="test_vault",
                permission="notanint"
            )
        codes = {e["field"]: e["code"] for e in ctx.exception.field_errors}
        self.assertEqual(codes["permission"], "INVALID_TYPE")

    def test_invalid_bool_raises_field_error(self):
        with self.assertRaises(ValidationError) as ctx:
            utils.unpack_into(
                _handler,
                client_id="client_1", vault="test_vault", permission="1",
                flag="yes"
            )
        codes = {e["field"]: e["code"] for e in ctx.exception.field_errors}
        self.assertEqual(codes["flag"], "INVALID_TYPE")

    def test_kwargs_extras_not_coerced(self):
        permission, rest = utils.unpack_into(
            _kwargs_handler, permission="1", extra="2"
        )
        self.assertEqual(permission, 1)
        self.assertEqual(rest, {"extra": "2"})


if __name__ == "__main__":
    unittest.main()
