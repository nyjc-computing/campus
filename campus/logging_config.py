"""campus.logging_config

This module configures logging for the Campus application, with special
attention to OAuth flow debugging.

The DEBUG level for the OAuth proxy modules is OPT-IN (default off):
those modules handle flow secrets (authorization codes, device/user
codes), and Railway stdout is a shared superadmin surface — policy §3
bans secrets from logs, so debug verbosity there must be a deliberate
act, never a default. The historical `campus.apps.oauth.*` logger names
matched nothing after the package split, which silently disabled the
debug tier anyway; the names now point at the real modules, so the
default had to flip to off to keep prod behavior unchanged (#1126).
"""

import logging
import sys

# Default logging configuration
DEFAULT_LOG_LEVEL = logging.INFO
OAUTH_LOG_LEVEL = logging.DEBUG

# Log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# The real OAuth-flow modules (post-split layout). basicConfig(force=True)
# already routes every logger to stdout with LOG_FORMAT, so enabling a
# tier is a setLevel — per-logger handlers would double-log.
OAUTH_LOGGERS = [
    'campus.auth.oauth_proxy.google',
    'campus.auth.oauth_proxy.github',
    'campus.auth.oauth_proxy.discord',
    'campus.auth.routes',
]


def configure_logging(
        log_level: int = DEFAULT_LOG_LEVEL,
        enable_oauth_debug: bool = False,
) -> None:
    """Configure logging for the Campus application.

    Idempotent: basicConfig(force=True) replaces prior root handlers,
    so repeated calls (main import, wsgi, tests) never stack handlers
    or double-log (#1126).

    Args:
        log_level: The default logging level for the application
        enable_oauth_debug: Whether to enable DEBUG level logging for
            the OAuth flow modules. Opt-in (default off): those modules
            handle flow secrets, and their DEBUG output must never
            reach production stdout by accident (#1126).
    """
    # Configure root logger (force=True clears existing handlers)
    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stdout,
        force=True
    )

    # Configure OAuth-specific loggers for debugging
    if enable_oauth_debug:
        for logger_name in OAUTH_LOGGERS:
            logging.getLogger(logger_name).setLevel(OAUTH_LOG_LEVEL)

    # Quiet down noisy third-party loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    logging.info("Logging configuration complete")
    if enable_oauth_debug:
        logging.info("OAuth debug logging enabled")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: The name of the logger (typically __name__)

    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)
