"""Logging configuration for Campus application.

This module configures logging for the Campus application, with special
attention to OAuth flow debugging.
"""

import logging
import sys
from typing import Any

# Default logging configuration
DEFAULT_LOG_LEVEL = logging.INFO
OAUTH_LOG_LEVEL = logging.DEBUG

# Log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def configure_logging(log_level: int = DEFAULT_LOG_LEVEL, enable_oauth_debug: bool = True) -> None:
    """Configure logging for the Campus application.

    Args:
        log_level: The default logging level for the application
        enable_oauth_debug: Whether to enable DEBUG level logging for OAuth flow
    """
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stdout,
        force=True
    )

    # Configure OAuth-specific loggers for debugging
    if enable_oauth_debug:
        oauth_loggers = [
            'campus.apps.oauth.google',
            'campus.apps.oauth.github',
            'campus.apps.oauth.discord',
            'campus.apps.campusauth.routes',
        ]

        for logger_name in oauth_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(OAUTH_LOG_LEVEL)

            # Add a handler with more detailed formatting for OAuth
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(OAUTH_LOG_LEVEL)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
                datefmt=DATE_FORMAT
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

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
