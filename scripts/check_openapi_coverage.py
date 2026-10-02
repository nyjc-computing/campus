#!/usr/bin/env python3
"""Check campus/auth/docs/openapi.yaml against the live Flask route map.

One-pass rewrite guard (PR after #712): every Flask operation must
appear in the spec and vice versa, and every internal $ref must
resolve. Exits non-zero on any drift. Not currently wired into CI —
run it after changing auth routes or the spec:

    DEPLOY=campus.auth SECRET_KEY=dummy \\
        .venv/Scripts/python.exe scripts/check_openapi_coverage.py
"""

import os
import re
import sys

os.environ.setdefault("DEPLOY", "campus.auth")
os.environ.setdefault("SECRET_KEY", "check-openapi-coverage-dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flask  # noqa: E402
import yaml  # noqa: E402

from campus.auth import init_app  # noqa: E402

SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "campus", "auth", "docs", "openapi.yaml",
)

HTTP_METHODS = {"get", "post", "patch", "delete", "put"}


def spec_operations(spec: dict) -> set[tuple[str, str]]:
    operations = set()
    for path, item in spec["paths"].items():
        for method in item:
            if method in HTTP_METHODS:
                operations.add((method.upper(), path))
    return operations


def flask_operations() -> set[tuple[str, str]]:
    app = flask.Flask(__name__)
    init_app(app)
    operations = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/static"):
            continue
        path = re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            operations.add((method, path))
    return operations


def broken_refs(spec: dict) -> list[str]:
    errors = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str) and value.startswith("#/"):
                    cursor = spec
                    for part in value[2:].split("/"):
                        if isinstance(cursor, dict) and part in cursor:
                            cursor = cursor[part]
                        else:
                            errors.append(f"{path}: broken ref {value}")
                            break
                else:
                    walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(spec)
    return errors


def main() -> int:
    with open(SPEC_PATH, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)

    spec_ops = spec_operations(spec)
    live_ops = flask_operations()

    missing = sorted(live_ops - spec_ops)
    extra = sorted(spec_ops - live_ops)
    refs = broken_refs(spec)

    print(f"flask operations: {len(live_ops)}, spec operations: {len(spec_ops)}")
    for op in missing:
        print(f"MISSING FROM SPEC: {op[0]:7s} {op[1]}")
    for op in extra:
        print(f"NOT IN FLASK:      {op[0]:7s} {op[1]}")
    for err in refs:
        print(f"BROKEN REF:        {err}")

    if missing or extra or refs:
        return 1
    print("openapi.yaml matches the Flask route map")
    return 0


if __name__ == "__main__":
    sys.exit(main())
