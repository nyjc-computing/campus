import unittest
from flask import Flask
from common.validation import flask as flask_validation
from common.validation import record as record_validation

class TestSchemaValidation(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.testing = True
        self.app.config['PROPAGATE_EXCEPTIONS'] = True
        self.client = self.app.test_client()

    def test_validate_decorator_valid_request_and_response(self):
        """Test that the validate decorator passes valid request and response schemas."""
        schema = {'foo': str, 'bar': int}
        response_schema = {'result': str}

        def error_handler(status, **body):
            raise Exception(f"Should not be called: {status}")

        @self.app.route('/test', methods=['POST'])
        @flask_validation.unpack_request_json
        @flask_validation.validate(
            request=schema,
            response=response_schema,
            on_error=error_handler
        )
        def test_view(*args: str, **payload):
            return {'result': f"{payload['foo']}-{payload['bar']}"}, 200

        with self.app.test_client() as c:
            resp = c.post('/test', json={'foo': 'baz', 'bar': 1})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json(), {'result': 'baz-1'})

    def test_validate_decorator_invalid_request(self):
        """Test that the validate decorator calls on_error for invalid request schema and that it must raise."""
        schema = {'foo': str, 'bar': int}
        called = {}
        class CustomError(Exception): pass
        def on_error(status, **body):
            called['status'] = status
            raise CustomError("error handler called")

        @self.app.route('/test_invalid', methods=['POST'])
        @flask_validation.unpack_request_json
        @flask_validation.validate(request=schema, on_error=on_error)
        def test_view_invalid(*args: str, **payload):
            return {'result': f"{payload['foo']}-{payload['bar']}"}, 200

        with self.app.test_client() as c:
            with self.assertRaises(CustomError):
                c.post('/test_invalid', json={'foo': 'baz'})  # missing 'bar'
            self.assertEqual(called.get('status'), 400)

    def test_validate_decorator_invalid_response(self):
        """Test that the validate decorator calls on_error for invalid response schema and that it must raise."""
        schema = {'foo': str}
        response_schema = {'result': int}
        called = {}
        class CustomError(Exception): pass
        def on_error(status, **body):
            called['status'] = status
            raise CustomError("error handler called")

        @self.app.route('/test_invalid_resp', methods=['POST'])
        @flask_validation.unpack_request_json
        @flask_validation.validate(
            request=schema,
            response=response_schema,
            on_error=on_error
        )
        def test_view_invalid_resp(*_: str, **__):
            return {'result': 'not-an-int'}, 200

        with self.app.test_client() as c:
            with self.assertRaises(CustomError):
                c.post('/test_invalid_resp', json={'foo': 'baz'})
            self.assertEqual(called.get('status'), 500)

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
