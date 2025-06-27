"""apps/api/models/auth/authentication/oauth2

OAuth2 security scheme configs and models.

The OAuth2 security scheme comprises four flows:
1. Authorization Code Flow: Used for web applications.
2. Client Credentials Flow: Used for server-to-server communication (not used in Campus).
3. Implicit Flow: Used for single-page applications (not used in Campus).
4. Password Flow: Used for resource owner password credentials (not used in Campus).
"""

from apps.api.models.auth.oauth2.authorization_code import OAuth2AuthorizationCodeFlowScheme
from apps.api.models.auth.oauth2.base import OAuth2FlowScheme


OAuth2FlowScheme.register_flow("authorizationCode", OAuth2AuthorizationCodeFlowScheme)


__all__ = [
    "OAuth2AuthorizationCodeFlowScheme",
]