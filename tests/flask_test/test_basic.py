"""tests.flask_test.test_basic

Basic tests for TestCampusRequest functionality.
"""

import unittest

import flask

from tests.flask_test import TestCampusRequest, FlaskTestResponse, register_test_app


class TestFlaskTestResponse(unittest.TestCase):
    """Test FlaskTestResponse adapter functionality."""

    def setUp(self):
        """Set up test Flask app."""
        self.app = flask.Flask(__name__)

        @self.app.route('/success')
        def success():
            return {'message': 'success'}, 200

        @self.app.route('/error')
        def error():
            return {'error': 'not found'}, 404

        @self.app.route('/json')
        def json_endpoint():
            return {'data': [1, 2, 3], 'count': 3}

    def test_response_properties(self):
        """Test basic response properties."""
        with self.app.test_client() as client:
            response = FlaskTestResponse(client.get('/success'))

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.ok())
            self.assertFalse(response.client_error())
            self.assertFalse(response.server_error())

    def test_json_response(self):
        """Test JSON response parsing."""
        with self.app.test_client() as client:
            response = FlaskTestResponse(client.get('/json'))

            json_data = response.json()
            self.assertEqual(json_data['data'], [1, 2, 3])
            self.assertEqual(json_data['count'], 3)

    def test_headers(self):
        """Test headers conversion."""
        with self.app.test_client() as client:
            response = FlaskTestResponse(client.get('/success'))

            headers = response.headers
            self.assertIsInstance(headers, dict)
            self.assertIn('Content-Type', headers)

    def test_error_status(self):
        """Test error status detection."""
        with self.app.test_client() as client:
            response = FlaskTestResponse(client.get('/error'))

            self.assertEqual(response.status_code, 404)
            self.assertFalse(response.ok())
            self.assertTrue(response.client_error())
            self.assertFalse(response.server_error())


class TestTestCampusRequest(unittest.TestCase):
    """Test TestCampusRequest adapter functionality."""

    def setUp(self):
        """Set up test Flask app."""
        self.app = flask.Flask(__name__)

        @self.app.route('/get-test')
        def get_test():
            return {'method': 'GET'}

        @self.app.route('/post-test', methods=['POST'])
        def post_test():
            import flask
            data = flask.request.get_json() or {}
            return {'method': 'POST', 'received': data}

        @self.app.route('/put-test', methods=['PUT'])
        def put_test():
            return {'method': 'PUT'}

        @self.app.route('/delete-test', methods=['DELETE'])
        def delete_test():
            return {'method': 'DELETE'}

        @self.app.route('/patch-test', methods=['PATCH'])
        def patch_test():
            return {'method': 'PATCH'}

        # Register app for testing
        register_test_app("https://campus.test", self.app, path_prefix="")

    def test_get_request(self):
        """Test GET request handling."""
        client = TestCampusRequest(base_url="https://campus.test")
        response = client.get('/get-test')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['method'], 'GET')

    def test_post_request(self):
        """Test POST request with JSON."""
        client = TestCampusRequest(base_url="https://campus.test")
        test_data = {'key': 'value', 'number': 42}
        response = client.post('/post-test', json=test_data)

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data['method'], 'POST')
        self.assertEqual(json_data['received'], test_data)

    def test_put_request(self):
        """Test PUT request handling."""
        client = TestCampusRequest(base_url="https://campus.test")
        response = client.put('/put-test')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['method'], 'PUT')

    def test_delete_request(self):
        """Test DELETE request handling."""
        client = TestCampusRequest(base_url="https://campus.test")
        response = client.delete('/delete-test')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['method'], 'DELETE')

    def test_patch_request(self):
        """Test PATCH request handling."""
        client = TestCampusRequest(base_url="https://campus.test")
        response = client.patch('/patch-test')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['method'], 'PATCH')


if __name__ == '__main__':
    unittest.main()
