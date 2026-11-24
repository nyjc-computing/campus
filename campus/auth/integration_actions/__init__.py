"""campus.auth.integration_actions

Integration action proxies (#1221): admin-authorized endpoints that
perform an upstream-provider verb (e.g. Classroom turnIn) on a TARGET
user's stored credential at an administrator's request.

Custody invariant (user decision on #1221): the provider's tokens stay
internal to campus.auth and never cross a service boundary. The
credential is loaded, silently refreshed, and scope-checked in-process
(`credentials.load_released_credential`, mirroring the broker's
release flow) and handed only to the in-process REST caller
(`classroom.py`). No response ever carries token material.

Modules:
- credentials: the released-credential loader (broker-invariant mirror)
- classroom: the Google Classroom REST verbs (allowlisted)
- routes: the HTTP surface with the #1221 authority gate
"""

from . import routes

__all__ = ["routes"]
