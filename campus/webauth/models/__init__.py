"""campus.webauth.models

Deprecated compatibility shim.

The header models moved to campus.model.http (#982). Import them from
campus.model instead. This shim exists only for campus_python, whose
json_client still imports campus.webauth.models; it is removed once
the SDK import flips to campus.model.
"""

__all__ = [
    "HttpAuthProperty",
    "HttpHeader",
    "HttpHeaderWithAuth",
]

from campus.model import HttpAuthProperty, HttpHeader, HttpHeaderWithAuth
