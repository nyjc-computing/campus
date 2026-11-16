"""campus.audit.ui_redirect

Redirects for the audit web UI's old URLs.

The audit web UI moved out of campus.audit into the campus-admin
portal (the pages had been reading this service's resources layer
in-process; the portal proxies the versioned API instead). The old
page URLs — /audit/, /audit/traces, /audit/keys, /audit/login, … —
kept working through the gateway and old bookmarks only if this
service answers them, so every GET under /audit that is not the
versioned API lands here:

- AUDIT_UI_URL set (the portal deployment's origin): 302 to the same
  path on the portal, query string preserved.
- AUDIT_UI_URL unset: a short notice page saying where the UI moved,
  so old links degrade into an explanation rather than a 404.

/audit/v1/* keeps its API-key authentication and is untouched; / is
the generic campus landing page (#842), since the service no longer
has a web UI of its own.
"""

__all__ = ["create_blueprint"]

import flask
import werkzeug

from campus.common import env


def _ui_base_url() -> str | None:
    """The portal origin hosting the audit web UI, or None."""
    return env.get("AUDIT_UI_URL") or None


def create_blueprint() -> flask.Blueprint:
    """Create the blueprint redirecting old UI URLs to the portal."""
    bp = flask.Blueprint(
        'audit_ui_redirect',
        __name__,
        url_prefix='/audit',
    )

    def _moved_page() -> flask.Response:
        target = _ui_base_url()
        if target:
            body = (
                f'<p>The audit web UI moved to the campus-admin portal: '
                f'<a href="{target}/audit/">{target}/audit/</a>.</p>'
                '<p>You are being redirected; bookmark the new address.</p>'
            )
        else:
            body = (
                '<p>The audit web UI moved to the campus-admin portal. '
                'Set AUDIT_UI_URL on this deployment to make old links '
                'redirect there.</p>'
            )
        return flask.Response(
            f"<h1>Audit web UI moved</h1>{body}",
            status=200,
            mimetype="text/html",
        )

    @bp.get('/')
    @bp.get('/<path:page>')
    def redirect_old_ui(page: str | None = None) -> werkzeug.Response:
        """Send old UI URLs to the portal (or explain where it moved)."""
        if page and page.startswith("v1"):
            # Anything under the versioned API is the service's real
            # surface: an unknown API route must 404 for API clients,
            # not bounce a machine caller to a portal page.
            flask.abort(404)
        target = _ui_base_url()
        if target:
            new_path = flask.request.full_path
            if new_path.endswith("?"):
                new_path = new_path.rstrip("?")
            return flask.redirect(f"{target}{new_path}", code=302)
        return _moved_page()

    return bp
