"""campus.webauth.models

Data models for web authentication.
"""

__all__ = [
    "HttpAuthProperty",
    "HttpHeader",
    "HttpHeaderWithAuth",
]

from .header import HttpAuthProperty, HttpHeader, HttpHeaderWithAuth
