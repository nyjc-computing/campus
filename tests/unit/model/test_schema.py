"""Unit tests for campus schema."""

import unittest

from campus.common import schema


class TestBoolean(unittest.TestCase):
    """Tests for the Boolean class."""

    @unittest.skip("Not implemented")
    def test_boolean_validation(self) -> None:
        """Response should raise TypeError when a non-bool value is
        passed.
        """
        with self.assertRaises(TypeError):
            schema.Boolean.raise_for_validation(1)
        with self.assertRaises(TypeError):
            schema.Boolean.raise_for_validation(1.5)
        with self.assertRaises(TypeError):
            schema.Boolean.raise_for_validation("1")
        with self.assertRaises(TypeError):
            schema.Boolean.raise_for_validation(None)


class TestInteger(unittest.TestCase):
    """Tests for the Integer class."""

    @unittest.skip("Not implemented")
    def test_bint_validation(self) -> None:
        """Response should raise TypeError when a non-int value is
        passed.
        """
        with self.assertRaises(TypeError):
            schema.Integer.raise_for_validation(False)
        with self.assertRaises(TypeError):
            schema.Integer.raise_for_validation(1.5)
        with self.assertRaises(TypeError):
            schema.Integer.raise_for_validation("1")
        with self.assertRaises(TypeError):
            schema.Integer.raise_for_validation(None)


class TestNumber(unittest.TestCase):
    """Tests for the Number class."""

    @unittest.skip("Not implemented")
    def test_number_validation(self) -> None:
        """Response should raise TypeError when a non-float value is
        passed.
        """
        with self.assertRaises(TypeError):
            schema.Number.raise_for_validation(1)
        with self.assertRaises(TypeError):
            schema.Number.raise_for_validation(True)
        with self.assertRaises(TypeError):
            schema.Number.raise_for_validation("1")
        with self.assertRaises(TypeError):
            schema.Number.raise_for_validation(None)


class TestDate(unittest.TestCase):
    """Tests for the Date class."""

    @unittest.skip("Not implemented")
    def test_boolean_validation(self) -> None:
        """Response should raise TypeError when a non-date value is
        passed.
        """
        with self.assertRaises(TypeError):
            schema.Date.raise_for_validation(1)
        with self.assertRaises(TypeError):
            schema.Date.raise_for_validation(1.5)
        with self.assertRaises(TypeError):
            schema.Date.raise_for_validation("1")
        with self.assertRaises(TypeError):
            schema.Date.raise_for_validation(None)
        with self.assertRaises(TypeError):
            schema.Date.raise_for_validation(True)



class TestString(unittest.TestCase):
    """Tests for the String class."""

    @unittest.skip("Not implemented")
    def test_string_validation(self) -> None:
        """Response should raise TypeError when a non-string value is
        passed.
        """
        with self.assertRaises(TypeError):
            schema.String.raise_for_validation(1)
        with self.assertRaises(TypeError):
            schema.String.raise_for_validation(1.5)
        with self.assertRaises(TypeError):
            schema.String.raise_for_validation(False)
        with self.assertRaises(TypeError):
            schema.String.raise_for_validation(None)


class TestDateTime(unittest.TestCase):
    """Tests for the DateTime class."""

    @unittest.skip("Not implemented")
    def test_boolean_validation(self) -> None:
        """Response should raise TypeError when a non-datetime value is
        passed.
        """
        with self.assertRaises(TypeError):
            schema.DateTime.raise_for_validation("123")
        with self.assertRaises(TypeError):
            schema.DateTime.raise_for_validation("1.5")
        with self.assertRaises(TypeError):
            schema.DateTime.raise_for_validation("1")
        with self.assertRaises(TypeError):
            schema.DateTime.raise_for_validation("1234")


class TestTime(unittest.TestCase):

    @unittest.skip("Not implemented")
    def test_string_validation(self) -> None:
        """Response should raise ValueError when a non-HHMM string is
        passed.
        """
        # Valid time; should not raise an error
        schema.String.raise_for_validation("1234")
        with self.assertRaises(ValueError):
            schema.String.raise_for_validation("9876")
        with self.assertRaises(ValueError):
            schema.String.raise_for_validation("12")
        with self.assertRaises(ValueError):
            schema.String.raise_for_validation("0")


class TestEmail(unittest.TestCase):

    @unittest.skip("Not implemented")
    def test_email_validation(self) -> None:
        """Response should raise ValueError when a non-valid email is
        passed.
        """
        with self.assertRaises(ValueError):
            schema.Email.raise_for_validation("example.com")
        with self.assertRaises(ValueError):
            schema.Email.raise_for_validation("@example.com")
        with self.assertRaises(ValueError):
            schema.Email.raise_for_validation("123")
        with self.assertRaises(ValueError):
            schema.Email.raise_for_validation("user")
