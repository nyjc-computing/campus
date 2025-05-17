import unittest
from flask import Flask, Request, json
from common.validation import flask as flask_validation
from common.validation import record as record_validation

class TestSchemaValidation(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.client = self.app.test_client()

    def test_unpack_json_valid(self):
        with self.app.test_request_context(
            '/', method='POST', json={'foo': 'bar'}
        ):
            result = flask_validation.unpack_json(flask_validation.flask_request, lambda s: self.fail(f"Error handler called with status {s}"))
            self.assertEqual(result, {'foo': 'bar'})

    def test_unpack_json_invalid_json(self):
        with self.app.test_request_context(
            '/', method='POST', data='notjson', content_type='application/json'
        ):
            called = {}
            def on_error(status):
                called['status'] = status
            result = flask_validation.unpack_json(flask_validation.flask_request, on_error)
            self.assertIsNone(result)
            self.assertIn('status', called)
            self.assertEqual(called['status'], 400)

    def test_unpack_json_wrong_mimetype(self):
        with self.app.test_request_context(
            '/', method='POST', data='{"foo": "bar"}', content_type='text/plain'
        ):
            called = {}
            def on_error(status):
                called['status'] = status
            result = flask_validation.unpack_json(flask_validation.flask_request, on_error)
            self.assertIsNone(result)
            self.assertIn('status', called)
            self.assertEqual(called['status'], 415)

    def test_record_validate_keys_valid(self):
        schema = {'foo': str, 'bar': int}
        data = {'foo': 'baz', 'bar': 1}
        # Should not raise
        record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_missing_key(self):
        schema = {'foo': str, 'bar': int}
        data = {'foo': 'baz'}
        with self.assertRaises(KeyError):
            record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_wrong_type(self):
        schema = {'foo': str, 'bar': int}
        data = {'foo': 'baz', 'bar': 'notint'}
        with self.assertRaises(TypeError):
            record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_ignore_extra(self):
        schema = {'foo': str}
        data = {'foo': 'baz', 'extra': 123}
        # Should not raise
        record_validation.validate_keys(data, schema, ignore_extra=True, required=True)

    def test_record_validate_keys_no_ignore_extra(self):
        schema = {'foo': str}
        data = {'foo': 'baz', 'extra': 123}
        with self.assertRaises(KeyError):
            record_validation.validate_keys(data, schema, ignore_extra=False, required=True)

if __name__ == "__main__":
    unittest.main()
