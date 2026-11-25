"""The flask_test transport double (TestCampusRequest) against its own contract.

TestCampusRequest replaces campus_python's CampusRequest for every
cross-service call the integration and contract suites make, so a double
that drifts from the production client turns into failures that only happen
in the harness — and nothing else exercises the double:
tests/flask_test/test_basic.py is a smoke script outside every suite. These
tests pin its verb contract in the blocking unit suite; extend them whenever
the SDK's transport changes.

First gap pinned: put()/put_data()/delete()/patch() did not accept the
`query` argument the JsonClient ABC declares, and post_data() passed it to
the Flask test client as `query=` (its parameter is `query_string`) — a
TypeError on every such call.
"""

import os
import unittest
from unittest import mock

import flask

from tests.flask_test import TestCampusRequest, clear_test_apps, register_test_app

BASE_URL = "https://campus.test"


def echo_app() -> flask.Flask:
    """A Flask app that reports how a request arrived."""
    app = flask.Flask(__name__)

    @app.route('/echo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def echo():
        return {
            'method': flask.request.method,
            'query': dict(flask.request.args),
            'content_type': flask.request.content_type,
            'json': flask.request.get_json(silent=True),
            'body': flask.request.get_data(as_text=True),
        }

    return app


class TransportTestCase(unittest.TestCase):
    """Isolated app registry and ambient credentials."""

    client: TestCampusRequest

    def setUp(self):
        environ = mock.patch.dict(os.environ, {
            "ACCESS_TOKEN": "audit_v1_ambienttracingkey00",
        })
        environ.start()
        self.addCleanup(environ.stop)

        register_test_app(BASE_URL, echo_app(), path_prefix="")
        self.addCleanup(clear_test_apps)

        self.client = TestCampusRequest(base_url=BASE_URL)


class TestVerbQuery(TransportTestCase):
    """Every verb carries its `query` argument through, as the ABC declares."""

    QUERY = {'filename': 'plan.txt'}

    def test_get_sends_its_query(self):
        response = self.client.get('/echo', query=self.QUERY)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['query'], self.QUERY)

    def test_json_verbs_send_query_and_body(self):
        """put()/delete()/patch() take `query` alongside the JSON body."""
        for verb in ('put', 'delete', 'patch'):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)(
                    '/echo', json={'key': 'value'}, query=self.QUERY,
                )

                self.assertEqual(response.json(), {
                    'method': verb.upper(),
                    'query': self.QUERY,
                    'content_type': 'application/json',
                    'json': {'key': 'value'},
                    'body': '{"key": "value"}',
                })

    def test_raw_body_verbs_send_query_content_type_and_body(self):
        """put_data()/post_data() keep the body verbatim with the query."""
        for verb in ('put_data', 'post_data'):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)(
                    '/echo', data='raw bytes',
                    content_type='text/plain', query=self.QUERY,
                )

                self.assertEqual(response.json(), {
                    'method': verb.removesuffix('_data').upper(),
                    'query': self.QUERY,
                    'content_type': 'text/plain',
                    'json': None,
                    'body': 'raw bytes',
                })

    def test_raw_body_verbs_without_query_or_content_type(self):
        """A bare put_data()/post_data() call goes through.

        post_data() used to raise TypeError even with nothing optional
        supplied: it always forwarded `query=`.
        """
        for verb in ('put_data', 'post_data'):
            with self.subTest(verb=verb):
                response = getattr(self.client, verb)('/echo', data=b'raw bytes')

                self.assertEqual(response.json(), {
                    'method': verb.removesuffix('_data').upper(),
                    'query': {},
                    'content_type': None,
                    'json': None,
                    'body': 'raw bytes',
                })


if __name__ == "__main__":
    unittest.main()
