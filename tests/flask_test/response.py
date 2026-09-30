"""tests.flask_test.response

FlaskTestResponse adapter for Campus JsonResponse protocol.
"""

from typing import Any

from werkzeug.test import TestResponse


class FlaskTestResponse:
    """Adapter that wraps werkzeug.test.TestResponse to implement JsonResponse protocol.

    This class adapts Flask's test response to match the Campus JsonResponse interface,
    enabling seamless testing with Flask apps without actual HTTP requests.
    """

    def __init__(self, response: TestResponse):
        """Initialize with a Flask test response.

        Args:
            response: The werkzeug TestResponse to wrap
        """
        self._response = response

    @property
    def status_code(self) -> int:
        """HTTP status code of the response."""
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        """Returns headers of the response as a dict.

        Converts werkzeug Headers to plain dict[str, str].
        """
        return dict(self._response.headers.items())

    @property
    def text(self) -> str:
        """Returns the response body as a string."""
        return self._response.get_data(as_text=True)

    def ok(self) -> bool:
        """Returns True if the response status code is 2xx, False otherwise."""
        return 200 <= self.status_code < 300

    def client_error(self) -> bool:
        """Returns True if the response status code is 4xx, False otherwise."""
        return 400 <= self.status_code < 500

    def server_error(self) -> bool:
        """Returns True if the response status code is 5xx, False otherwise."""
        return 500 <= self.status_code < 600

    def raise_for_status(self) -> None:
        """Raises an exception if the response status code indicates an error.

        Mirrors campus_python's production JsonClient.raise_for_status():
        the error is built via APIError.with_status_code() so callers see
        exactly the same exception classes (campus_python.errors.*) under
        the Flask test routing as they would over a real connection.

        Raises:
            BadRequestError: If the status code is 400
            AuthenticationError: If the status code is 401
            AccessDeniedError: If the status code is 403
            NotFoundError: If the status code is 404
            ConflictError: If the status code is 409
            ValidationError: If the status code is 422
            APIError: For other 4xx/5xx status codes
        """
        from campus_python import errors as campus_python_errors

        if not (self.client_error() or self.server_error()):
            return

        try:
            response_data = self.json()
        except Exception:
            response_data = None
        if not isinstance(response_data, (dict, str)):
            response_data = self.text

        error = campus_python_errors.APIError.with_status_code(
            self.status_code, response_data
        )
        if error is not None:
            raise error from None

    def json(self) -> Any:
        """Returns the response body as JSON."""
        return self._response.get_json()
