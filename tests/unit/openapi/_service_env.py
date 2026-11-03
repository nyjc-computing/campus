"""Shared fixtures for OpenAPI artifact/serving tests (#1029).

Bootstraps the same environment the contract suite uses (test storage
backends, no external services) but WITHOUT the flask_test
campus_python patch, so nothing leaks into the rest of the unit-suite
process. Callers snapshot/restore os.environ around app creation.
"""

import importlib
import os
import pathlib
import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

SERVICES = ("campus.auth", "campus.api", "campus.audit")


def artifact_path(service: str) -> pathlib.Path:
    return REPO_ROOT / service.replace(".", "/") / "docs" / "openapi.json"


def suite_version() -> str:
    """The declared campus-suite version, read from pyproject.toml.

    pyproject (not importlib.metadata) is the source: editable-install
    metadata goes stale between a version bump and the next venv sync.
    """
    data = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return data["tool"]["poetry"]["version"]


def bootstrap():
    """One-time env/storage setup before creating service apps."""
    from campus.common import env
    from tests.fixtures import auth as auth_fixture
    from tests.fixtures import setup
    from tests.fixtures import yapper as yapper_fixture

    env.set("ENV", env.TESTING)
    setup.set_test_env_vars()
    import campus.storage.testing

    campus.storage.testing.configure_test_storage()
    env.set("CAMPUS_AUTH_URL", "https://campus.test")
    env.set("CAMPUS_API_URL", "https://campus.test")
    env.set("PUBLIC_URL", "https://campus.test")
    auth_fixture.init()
    yapper_fixture.init()


def make_app(service: str):
    """Create the service's Flask app via deploy.create_app."""
    os.environ["DEPLOY"] = service
    os.environ["AUDIT_TRACING_ENABLED"] = "0"
    os.environ["AUDIT_EVENTS_ENABLED"] = "0"
    from campus.deploy import create_app

    return create_app(importlib.import_module(service))


def build_spec(service: str, version: str) -> dict:
    """Generate the service's spec via the generator (no artifact read)."""
    from campus.flask_campus import openapi

    return openapi.build_spec_from_module(service, version=version)
