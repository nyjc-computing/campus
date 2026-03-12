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
        return {k: v for k, v in self._response.headers.items()}

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

        Raises:
            AuthenticationError: If the status code is 401
            AccessDeniedError: If the status code is 403
            NotFoundError: If the status code is 404
            ConflictError: If the status code is 409
            InvalidRequestError: If the status code is 400 or 422
            HttpClientError: For other 4xx or 5xx status codes
        """
        from campus.common.http.errors import (
            AuthenticationError,
            AccessDeniedError,
            NotFoundError,
            ConflictError,
            InvalidRequestError,
            HttpClientError,
        )

        if not (self.client_error() or self.server_error()):
            return

        status = self.status_code
        message = self.text

        match status:
            case 400:
                raise InvalidRequestError(f"{status} Bad Request: {message}")
            case 401:
                raise AuthenticationError(f"{status} Unauthorized: {message}")
            case 403:
                raise AccessDeniedError(f"{status} Forbidden: {message}")
            case 404:
                raise NotFoundError(f"{status} Not Found: {message}")
            case 409:
                raise ConflictError(f"{status} Conflict: {message}")
            case 422:
                raise InvalidRequestError(
                    f"{status} Unprocessable Entity: {message}")
            case _:
                # Generic error for other 4xx/5xx codes
                raise HttpClientError(f"{status} HTTP Error: {message}")

    def json(self) -> Any:
        """Returns the response body as JSON."""
        return self._response.get_json()
