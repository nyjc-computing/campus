"""Regenerate the committed OpenAPI artifacts for Campus services (#1029).

Usage:
    poetry run python scripts/generate_openapi.py            # all services
    poetry run python scripts/generate_openapi.py campus.auth

Generates each service's spec from its Flask app object via
campus.flask_campus.openapi and writes the deterministic JSON artifact
to campus/{service}/docs/openapi.json, pinned to the campus-suite
version from pyproject.toml.

After regenerating (any PR that changes routes or handler docstrings):
bump the campus-suite version in pyproject.toml — minor for spec
changes, patch for API-preserving changes — and rerun
tests/run_tests.py unit; the drift/pin tests must stay green.

Generation builds the service apps, so it runs against the test
fixtures (in-memory/sqlite storage, no external services) — the same
recipe tests/unit/openapi/_service_env.py uses.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tests.unit.openapi import _service_env  # noqa: E402


def main(argv: list[str]) -> int:
    services = argv[1:] or list(_service_env.SERVICES)
    unknown = [s for s in services if s not in _service_env.SERVICES]
    if unknown:
        print(f"Unknown service(s): {', '.join(unknown)}; "
              f"known: {', '.join(_service_env.SERVICES)}")
        return 2

    import os

    saved = dict(os.environ)
    try:
        _service_env.bootstrap()
        version = _service_env.suite_version()
        for service in services:
            spec = _service_env.build_spec(service, version)
            out = _service_env.artifact_path(service)
            from campus.flask_campus import openapi

            openapi.write_spec(spec, out)
            print(f"{service}: {len(spec['paths'])} paths -> {out} "
                  f"(v{version})")
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
