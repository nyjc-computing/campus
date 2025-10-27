"""campus.models.session

Session model for the Campus API.

This module defines session management for the Campus API.

For authenticated HTTP requests in the Campus API, clients must include 
the session_id (in cookie), client_id (in header), and access_token (in header).
user_id is retrieved from the session record.
The access token itself is not stored in sessions; it's validated per-request.
"""

__all__ = [
    'AuthSessionRecord',
    'AuthSessions',
    'LoginSessionRecord',
    'LoginSessions',
]

from .auth import AuthSessionRecord, AuthSessions
from .login import LoginSessionRecord, LoginSessions
