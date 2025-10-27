import unittest
from flask import Flask
from campus.common.validation import flask as flask_validation
from campus.common.validation import record as record_validation

class TestSchemaValidation(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.testing = True
        self.app.config['PROPAGATE_EXCEPTIONS'] = True
        self.client = self.app.test_client()

    def test_record_validate_keys_valid(self):
        """Test that validate_keys passes for valid data and schema."""
        schema = {'foo': str, 'bar': int}
        data = {'foo': 'baz', 'bar': 1}
        # Should not raise
        record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_missing_key(self):
        """Test that validate_keys raises KeyError for missing required keys."""
        schema = {'foo': str, 'bar': int}
        data = {'foo': 'baz'}
        with self.assertRaises(KeyError):
            record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_wrong_type(self):
        """Test that validate_keys raises TypeError for wrong value types."""
        schema = {'foo': str, 'bar': int}
        data = {'foo': 'baz', 'bar': 'notint'}
        with self.assertRaises(TypeError):
            record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_ignore_extra(self):
        """Test that validate_keys ignores extra keys when ignore_extra is True."""
        schema = {'foo': str}
        data = {'foo': 'baz', 'extra': 123}
        # Should not raise
        record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_no_ignore_extra(self):
        """Test that validate_keys raises KeyError for extra keys when ignore_extra is False."""
        schema = {'foo': str}
        data = {'foo': 'baz', 'extra': 123}
        with self.assertRaises(KeyError):
            record_validation.validate_keys(data, schema, ignore_extra=False, required=True)

if __name__ == "__main__":
    unittest.main()
