"""campus.common.webauth.oauth2.device_authorization

OAuth2 Device Authorization Flow schemas and models.

Reference: https://datatracker.ietf.org/doc/html/rfc8628
"""

__all__ = ["OAuth2DeviceAuthorizationFlowScheme"]

from typing import Any

import requests

from campus.common import schema
from campus.common.errors import auth_errors, token_errors
from campus.common.utils import url, secret, uid
import campus.model

from . import base

# Default expiry time for device codes in seconds
DEVICE_CODE_EXPIRY_SECONDS = 600  # 10 minutes
# Default polling interval in seconds
DEFAULT_POLL_INTERVAL = 5
# Default timeout for requests in seconds
TIMEOUT = 10


class OAuth2DeviceAuthorizationFlowScheme(base.OAuth2FlowScheme):
    """Configures OAuth2 Device Authorization Flow (RFC 8628).

    This flow is designed for devices that have limited input capabilities
    or lack a suitable browser for user interaction. It's also ideal for CLI
    applications where embedding a client secret is not feasible.

    The flow works as follows:
    1. Client requests a device code from the authorization server
    2. Server returns a device code, user code, and verification URI
    3. User visits the verification URI and enters the user code
    4. Client polls the token endpoint until the user completes authorization
    5. Server returns tokens when authorization completes
    """

    flow = "deviceCode"
    device_code_url: schema.Url
    token_url: schema.Url
    verification_uri: schema.Url
    verification_uri_complete: schema.Url | None
    headers: dict[str, str]
    scopes: list[str]

    def __init__(
            self,
            provider: str,
            client_id: str,
            device_code_url: schema.Url,
            token_url: schema.Url,
            verification_uri: schema.Url,
            scopes: list[str],
            verification_uri_complete: schema.Url | None = None,
            headers: dict[str, str] | None = None,
    ):
        super().__init__(provider)
        self.client_id = client_id
        self.device_code_url = device_code_url
        self.token_url = token_url
        self.verification_uri = verification_uri
        self.verification_uri_complete = verification_uri_complete
        self.scopes = scopes
        self.headers = headers or {}

    def request_device_code(
            self,
    ) -> dict[str, Any]:
        """Request a device code from the authorization server.

        Returns:
            Dict containing:
            - device_code: The device code for polling
            - user_code: The code the user must enter
            - verification_uri: The URI where the user enters the code
            - verification_uri_complete: The URI with user_code pre-filled (optional)
            - expires_in: Seconds until the device code expires
            - interval: Minimum seconds between polling attempts

        Raises:
            auth_errors.TemporarilyUnavailableError: If the request times out
            token_errors.TokenError: If the request fails
        """
        params = {
            "client_id": self.client_id,
            "scope": " ".join(self.scopes),
        }
        try:
            resp = requests.post(
                self.device_code_url,
                data=params,
                headers=self.headers,
                timeout=TIMEOUT
            )
        except requests.exceptions.Timeout as err:
            raise auth_errors.TemporarilyUnavailableError(
                "Device code request timed out"
            ) from None

        payload = resp.json()
        if "error" in payload:
            token_errors.raise_from_json(payload)

        return payload

    def poll_for_token(
            self,
            device_code: str,
    ) -> campus.model.OAuthToken:
        """Poll the token endpoint for an access token.

        Args:
            device_code: The device code received from the authorization server

        Returns:
            OAuthToken instance

        Raises:
            token_errors.AuthorizationPendingError: User hasn't completed auth
            token_errors.SlowDownError: Client is polling too fast
            token_errors.ExpiredTokenError: Device code has expired
            token_errors.AccessDeniedError: User denied the authorization
            token_errors.TokenError: For other errors
        """
        params = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": self.client_id,
        }
        request_time = schema.DateTime.utcnow()
        try:
            resp = requests.post(
                self.token_url,
                data=params,
                headers=self.headers,
                timeout=TIMEOUT
            )
        except requests.exceptions.Timeout as err:
            raise auth_errors.TemporarilyUnavailableError(
                "Token request timed out"
            ) from None

        payload = resp.json()

        if "error" in payload:
            token_errors.raise_from_json(payload)

        return campus.model.OAuthToken(
            id=payload["access_token"],
            created_at=request_time,
            expiry_seconds=payload["expires_in"],
            scopes=payload.get("scope", "").split(" ") if "scope" in payload else [],
            **(
                {"refresh_token": payload["refresh_token"]}
                if "refresh_token" in payload
                else {}
            )
        )

    def get_verification_uri(self, user_code: str | None = None) -> schema.Url:
        """Get the verification URI for the user to visit.

        If verification_uri_complete is available and user_code is provided,
        returns the complete URI with the user code pre-filled.

        Args:
            user_code: Optional user code to pre-fill in the URI

        Returns:
            The verification URI
        """
        if user_code and self.verification_uri_complete:
            return schema.Url(url.create_url(
                hostname=self.verification_uri_complete,
                params={"user_code": user_code}
            ))
        return schema.Url(self.verification_uri)
