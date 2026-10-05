"""campus.audit.middleware.journeys

Action-journey lifecycle (#828).

A journey groups every trace belonging to one user-initiated action
episode: the page load that began it, the XHRs and form posts it fires,
and the server-to-server calls those spawn (joined via SDK-forwarded
X-Journey-ID headers). This is distinct from *login* journeys (#803),
which correlate the browser hops of the login flow itself via the
campus_journey cookie.

Lifecycle:

- **Adopt** an inbound journey from the X-Journey-ID header (an
  SDK-forwarded child call, or an app that mints client-side) or the
  campus_action_journey cookie (same-origin XHRs/form posts/redirect
  GETs carry it automatically).
- **Mint** a new journey on page navigations (Sec-Fetch-Mode: navigate
  or Accept: text/html) with no active journey — the navigation IS the
  user-initiated origin. Optional per registration: services with no
  browser surface (campus.api) or whose browser surface is the login
  flow itself (campus.auth, already covered by #803) register with
  ``mint_on_navigation=False`` and adopt only.
- **Continue** via the cookie: set/refreshed on every request that has
  an active journey, so a still-live cookie carries the episode across
  navigations too — deliberately, because a POST-redirect-GET result
  page cannot be distinguished from a fresh click, and splitting it
  would cut the action in half. Episodes stay action-sized through the
  sliding window instead: idle expiry (no request refreshes the cookie
  within ACTION_JOURNEY_COOKIE_MAX_AGE) ends the journey, and apps can
  mark hard boundaries with ``@journey(..., fresh=True)``. There is no
  explicit end state.

Trust stance matches X-Request-ID: journey ids are observability
correlation, not a security boundary — clients may forge them.
"""

__all__ = ["init_journeys", "current_journey", "ACTION_JOURNEY_HEADER"]

import typing

import flask

import campus.config
from campus.common.utils import uid

from . import tracing

# Mirror: campus_python.tracing forwards this header on SDK calls made
# while handling a journeyed request, so child services' spans join the
# same journey. Keep the two in lockstep.
ACTION_JOURNEY_HEADER = "X-Journey-ID"


def _is_navigation() -> bool:
    """True for browser page navigations (the journey-start request).

    Sec-Fetch-Mode: navigate is set by modern browsers; the Accept
    fallback covers clients that omit Fetch Metadata.
    """
    if flask.request.headers.get("Sec-Fetch-Mode") == "navigate":
        return True
    accept = flask.request.headers.get("Accept", "")
    return accept.startswith("text/html")


def _adopt_or_mint(*, mint: bool) -> None:
    """before_request: stash the request's journey id, if any.

    Precedence: explicit header (SDK-forwarded or app-minted) > action
    cookie (same-origin browser continuation) > mint on navigation.
    Static requests are skipped outright (#819): they cannot gain child
    spans and never begin an episode.
    """
    if tracing.is_static_request():
        return

    journey_id = (
        flask.request.headers.get(ACTION_JOURNEY_HEADER)
        or flask.request.cookies.get(campus.config.ACTION_JOURNEY_COOKIE)
    )
    if not journey_id and mint and _is_navigation():
        journey_id = uid.generate_category_uid("journey")
    if journey_id:
        flask.g.journey_id = journey_id


def _refresh_cookie(response: flask.Response) -> flask.Response:
    """after_request: set/refresh the journey cookie when one is active.

    Refreshing on every journeyed request makes the cookie a sliding
    idle window; a journey ends when no request refreshes it before the
    cookie expires (or when the next navigation mints a fresh id).
    """
    journey_id = getattr(flask.g, "journey_id", None)
    if journey_id:
        response.set_cookie(
            campus.config.ACTION_JOURNEY_COOKIE,
            journey_id,
            max_age=campus.config.ACTION_JOURNEY_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            path="/",
        )
    return response


def init_journeys(
        app: flask.Flask | flask.Blueprint,
        *,
        mint_on_navigation: bool = True,
) -> None:
    """Register the action-journey lifecycle on an app or blueprint.

    Args:
        app: The Flask app (or blueprint for scoped opt-in) whose
            requests participate in action journeys.
        mint_on_navigation: Mint a new journey on page navigations with
            no active journey. Services whose browser surface is already
            journeyed another way — campus.auth's login flow (#803) — or
            that serve no browser pages at all (campus.api) should pass
            False and adopt only: SDK-forwarded X-Journey-ID headers on
            their routes still join the caller's journey.
    """

    @app.before_request
    def _journey_before_request() -> None:
        _adopt_or_mint(mint=mint_on_navigation)

    @app.after_request
    def _journey_after_request(response: flask.Response) -> flask.Response:
        return _refresh_cookie(response)


def current_journey() -> typing.Optional[str]:
    """The active action journey id for this request, if any.

    None outside a request context or when no journey was adopted or
    minted. Exposed for the SDK forwarding path and diagnostics.
    """
    return getattr(flask.g, "journey_id", None)
