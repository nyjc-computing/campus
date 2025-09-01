"""campus.client.interface

Interface descriptions for the Campus client interface.

This interface is designed to:
- wrap `flask.testing.FlaskClient`
- wrap most common client interfaces e.g. `requests`
- provide a common Response interface that wraps `werkzeug.test.TestResponse,
  `requests.Response`, etc
- so aa to enable WSGI hooks or unit testing with a local WSGI app.
"""

from campus.common.http import JsonClient


class Resource:
    """Resource class that represents API resources

    The resource class uses a JsonClient instance to handle all API requests.
    It only tracks the path of the current resource.
    """
    client: JsonClient
    path: str

    def __init__(
            self,
            client_or_parent: "JsonClient | Resource",
            *parts: str
    ):
        match client_or_parent:
            case Resource():
                self.client = client_or_parent.client
                self.path = f"{client_or_parent.path}/{'/'.join(parts)}"
            case JsonClient():
                self.client = client_or_parent
                self.path = '/'.join(parts)

    def __repr__(self) -> str:
        return f"Resource(client={self.client}, path={self.path})"

    def __str__(self) -> str:
        return self.path

    def make_path(self, path: str) -> str:
        """Create a full path for a sub-resource or action."""
        return f"{self.path}/{path.lstrip('/')}"
