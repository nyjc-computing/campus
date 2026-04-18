"""campus.audit.web.ui

UI routes for the Audit Web UI - serves HTML templates for browsing traces.

This module contains web UI routes for the audit service, providing
a web interface for exploring and viewing audit traces.
"""

__all__ = ["create_blueprint"]

import flask


def create_blueprint() -> flask.Blueprint:
    """Create a Flask blueprint for UI routes.

    Returns:
        A Flask blueprint with UI route handlers
    """
    bp = flask.Blueprint(
        'audit_ui',
        __name__,
        url_prefix='/audit',
        template_folder='templates',
        static_folder='static'
    )

    @bp.route('/')
    def index() -> str:
        """Render the base template.

        This is the main entry point for the Audit Web UI.
        """
        return flask.render_template('base.html')

    @bp.route('/traces')
    def trace_list() -> str:
        """Render the trace list page.

        This page displays a list of audit traces with filtering capabilities.
        """
        return flask.render_template('trace_list.html')

    return bp
