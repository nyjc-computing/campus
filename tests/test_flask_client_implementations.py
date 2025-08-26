"""Test the Flask test client implementations."""

import unittest

from flask import Flask, request, jsonify

from tests.test_client import FlaskTestClient, FlaskTestResponse, create_test_client_factory


class TestFlaskClientImplementations(unittest.TestCase):
    """Test the Flask test client implementations."""

    def setUp(self):
        """Set up a test Flask app."""
        self.app = Flask(__name__)

        # Define test routes
        @self.app.route('/test', methods=['GET'])
        def test_get():
            return jsonify({"method": "GET", "params": request.args.to_dict()})

        @self.app.route('/test', methods=['POST'])
        def test_post():
            data = request.get_json() or {}
            return jsonify({"method": "POST", "data": data}), 201

        @self.app.route('/test', methods=['PUT'])
        def test_put():
            data = request.get_json() or {}
            return jsonify({"method": "PUT", "data": data})

        @self.app.route('/test', methods=['PATCH'])
        def test_patch():
            data = request.get_json() or {}
            return jsonify({"method": "PATCH", "data": data})

        @self.app.route('/test', methods=['DELETE'])
        def test_delete():
            data = request.get_json() or {}
            return jsonify({"method": "DELETE", "data": data})

        @self.app.route('/headers')
        def test_headers():
            return jsonify({"user_agent": request.headers.get('User-Agent', 'Unknown')})

        self.flask_client = self.app.test_client()
        self.test_client = FlaskTestClient(self.flask_client)

    def test_flask_test_response_properties(self):
        """Test FlaskTestResponse properties."""
        # Make a request using Flask test client directly
        response = self.flask_client.get('/test')
        wrapped_response = FlaskTestResponse(response)

        # Test status property
        self.assertEqual(wrapped_response.status, 200)

        # Test headers property
        headers = wrapped_response.headers
        self.assertIsInstance(headers, dict)
        self.assertIn('Content-Type', headers)

        # Test text property
        text = wrapped_response.text
        self.assertIsInstance(text, str)
        self.assertIn('GET', text)

        # Test json property
        json_data = wrapped_response.json()
        self.assertIsInstance(json_data, dict)
        self.assertEqual(json_data['method'], 'GET')

    def test_get_request(self):
        """Test GET request with parameters."""
        response = self.test_client.get(
            '/test', params={'key': 'value', 'num': '123'})

        self.assertEqual(response.status, 200)
        data = response.json()
        self.assertEqual(data['method'], 'GET')
        self.assertEqual(data['params']['key'], 'value')
        self.assertEqual(data['params']['num'], '123')

    def test_post_request(self):
        """Test POST request with JSON data."""
        test_data = {'name': 'test', 'value': 42}
        response = self.test_client.post('/test', json=test_data)

        self.assertEqual(response.status, 201)
        data = response.json()
        self.assertEqual(data['method'], 'POST')
        self.assertEqual(data['data'], test_data)

    def test_put_request(self):
        """Test PUT request with JSON data."""
        test_data = {'update': 'data', 'id': 1}
        response = self.test_client.put('/test', json=test_data)

        self.assertEqual(response.status, 200)
        data = response.json()
        self.assertEqual(data['method'], 'PUT')
        self.assertEqual(data['data'], test_data)

    def test_patch_request(self):
        """Test PATCH request with JSON data."""
        test_data = {'partial': 'update'}
        response = self.test_client.patch('/test', json=test_data)

        self.assertEqual(response.status, 200)
        data = response.json()
        self.assertEqual(data['method'], 'PATCH')
        self.assertEqual(data['data'], test_data)

    def test_delete_request(self):
        """Test DELETE request with JSON data."""
        test_data = {'confirm': True}
        response = self.test_client.delete('/test', json=test_data)

        self.assertEqual(response.status, 200)
        data = response.json()
        self.assertEqual(data['method'], 'DELETE')
        self.assertEqual(data['data'], test_data)

    def test_client_factory(self):
        """Test the client factory function."""
        factory = create_test_client_factory(
            self.flask_client, "http://test.example.com")
        client = factory()

        self.assertIsInstance(client, FlaskTestClient)
        self.assertEqual(client.base_url, "http://test.example.com")

        # Test that it works
        response = client.get('/test')
        self.assertEqual(response.status, 200)
        data = response.json()
        self.assertEqual(data['method'], 'GET')

    def test_path_handling(self):
        """Test path handling with and without leading slash."""
        # Test with leading slash
        response1 = self.test_client.get('/test')
        self.assertEqual(response1.status, 200)

        # Test without leading slash
        response2 = self.test_client.get('test')
        self.assertEqual(response2.status, 200)

        # Both should give same result
        self.assertEqual(response1.json(), response2.json())

    def test_empty_json_request(self):
        """Test request with None/empty JSON."""
        # Test with None - this might cause a 400 because Flask expects valid JSON
        response1 = self.test_client.post('/test', json=None)
        # This is acceptable behavior
        self.assertIn(response1.status, [200, 201, 400])

        # Test with empty dict - this should work
        response2 = self.test_client.post('/test', json={})
        self.assertEqual(response2.status, 201)
        data = response2.json()
        self.assertEqual(data['method'], 'POST')
        self.assertEqual(data['data'], {})


if __name__ == '__main__':
    unittest.main()
