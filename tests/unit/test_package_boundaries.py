"""Package boundary contract tests (#970).

Static (AST) and runtime checks that the shared/service layering agreed
for the campus-core carve-out holds. These make the future distribution
split mechanical: if the contract stays green, campus.common/config and
campus.model/storage/webauth/services can be packaged without pulling
service implementations, Flask, or database drivers.

Rules enforced:

1. Self-contained layers (common, config, model, storage, webauth,
   services, yapper) may only depend on the campus subpackages listed in
   SHARED_ALLOWED. yapper's entry is empty: it imports no campus package
   at all (its credentials/DB URI arrive via arguments or environment —
   #970 phase 2 removed the lazy campus.auth import).
2. Self-contained layers must not import a service layer (auth, api,
   audit, flask_campus, deploy) anywhere — module level or lazy.
3. Self-contained layers must not import flask/werkzeug at module level.
   The one documented exception is the emailotp template, which lazily
   imports flask at call time (inside body()/html_body()).
4. campus.common's only module-level third-party import is bcrypt
   (utils/secret.py). Requests used to ride in via the http client,
   which moved to campus.audit.http; this rule keeps it out.
5. Storage database drivers stay lazily imported: importing
   campus.storage must not load psycopg2/pymongo/boto3.

Runtime assertions run in subprocesses, because this test process may
legitimately have those modules loaded already.
"""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

CAMPUS_DIR = Path(__file__).resolve().parents[2] / "campus"

# campus subpackage -> set of campus subpackages it may depend on
SHARED_ALLOWED = {
    "common": set(),
    "config": {"common"},
    "model": {"common"},
    "storage": {"common", "model"},
    "webauth": {"common", "model"},
    "services": {"common"},
    # Self-contained: imports no campus package at all. Emitters (auth,
    # api) may import it; it must never grow campus dependencies back.
    "yapper": set(),
}

# Layer modules that self-contained layers must never import, even lazily.
SERVICE_LAYERS = {"auth", "api", "audit", "flask_campus", "deploy"}

# Third-party modules banned at module level in shared layers.
NO_MODULE_LEVEL = {"flask", "werkzeug"}

# Third-party modules campus.common may import at module level.
COMMON_THIRD_PARTY_ALLOWED = {"bcrypt"}


def _iter_shared_files():
    """Yield (subpackage, path) for every file of every shared layer."""
    for sub in SHARED_ALLOWED:
        root = CAMPUS_DIR / sub
        if root.is_dir():
            for path in sorted(root.rglob("*.py")):
                if "__pycache__" not in path.parts:
                    yield sub, path
    config = CAMPUS_DIR / "config.py"
    if config.is_file():
        yield "config", config


def _package_parts(path: Path) -> tuple[str, ...]:
    """Containing-package parts of a file under campus/.

    This is the anchor relative imports resolve against: the file's own
    path with the last part dropped — the same operation for both cases,
    because an __init__ file IS its package, while a module anchors at
    its containing package.

    campus/model/emailotp/template.py -> ("model", "emailotp")
    campus/model/base.py              -> ("model",)
    campus/model/__init__.py          -> ("model",)
    """
    parts = path.with_suffix("").relative_to(CAMPUS_DIR).parts
    return parts[:-1]


def _resolve_subpackage(module: str) -> str | None:
    """Map a dotted module name to its campus subpackage ('campus.X')."""
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "campus":
        return None
    return parts[1]


def _iter_import_targets(tree: ast.Module, package: tuple[str, ...]):
    """Yield (node, absolute dotted target) for every import in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Anchor of a relative import: the containing package for
                # one dot, its parent for two, ... — rooted at "campus" so
                # targets resolve through _resolve_subpackage (they are
                # otherwise invisible to the layering rules).
                anchor = package[: max(0, len(package) - node.level + 1)]
                base = ("campus", *anchor)
                if node.module:
                    yield node, ".".join([*base, *node.module.split(".")])
                else:
                    yield node, ".".join(base)
            elif node.module:
                yield node, node.module


class TestImportTargetResolution(unittest.TestCase):
    """Relative imports must resolve absolutely, or the rules skip them."""

    def _targets(self, source: str, package: tuple[str, ...]) -> set[str]:
        tree = ast.parse(source)
        return {target for _, target in _iter_import_targets(tree, package)}

    def test_relative_imports_anchor_at_campus_root(self):
        """One dot = containing package; each further dot = one level up."""
        self.assertEqual(
            self._targets("from .audit import APIKey\n", ("model",)),
            {"campus.model.audit"},
        )
        self.assertEqual(
            self._targets("from ..audit import spans\n", ("model",)),
            {"campus.audit"},
        )
        self.assertEqual(
            self._targets("from ...common import utils\n", ("model", "emailotp")),
            {"campus.common"},
        )
        self.assertEqual(
            self._targets("from . import template\n", ("model", "emailotp")),
            {"campus.model.emailotp"},
        )

    def test_package_parts_is_the_containing_package(self):
        """Module files anchor at their package; __init__ files at themselves."""
        self.assertEqual(_package_parts(CAMPUS_DIR / "model" / "base.py"), ("model",))
        self.assertEqual(
            _package_parts(CAMPUS_DIR / "model" / "emailotp" / "template.py"),
            ("model", "emailotp"),
        )
        self.assertEqual(_package_parts(CAMPUS_DIR / "model" / "__init__.py"), ("model",))


class TestSharedLayerImports(unittest.TestCase):
    """AST-level layering rules for the shared layers."""

    def test_shared_layers_import_within_allowed_set(self):
        """Test that shared layers depend only on permitted campus layers."""
        failures = []
        for sub, path in _iter_shared_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            package = _package_parts(path)
            for node, target in _iter_import_targets(tree, package):
                resolved = _resolve_subpackage(target)
                if resolved is None or resolved == sub:
                    continue
                lineno = getattr(node, "lineno", "?")
                if resolved in SERVICE_LAYERS:
                    failures.append(
                        f"{path.relative_to(CAMPUS_DIR.parent)}:{lineno} "
                        f"shared layer imports service layer: {target}"
                    )
                elif resolved not in SHARED_ALLOWED[sub]:
                    failures.append(
                        f"{path.relative_to(CAMPUS_DIR.parent)}:{lineno} "
                        f"{sub} imports outside SHARED_ALLOWED: {target}"
                    )
        if failures:
            self.fail("Boundary violations:\n" + "\n".join(sorted(failures)))

    def test_shared_layers_module_level_third_party(self):
        """Test that shared layers stay lean at module level."""
        for sub, path in _iter_shared_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    if top in sys.stdlib_module_names or top == "campus":
                        continue
                    if top in NO_MODULE_LEVEL:
                        self.fail(
                            f"{path.relative_to(CAMPUS_DIR.parent)}:{node.lineno} "
                            f"module-level {top} import in shared layer"
                        )
                    if sub == "common" and top not in COMMON_THIRD_PARTY_ALLOWED:
                        self.fail(
                            f"{path.relative_to(CAMPUS_DIR.parent)}:{node.lineno} "
                            f"campus.common module-level third-party import "
                            f"outside {sorted(COMMON_THIRD_PARTY_ALLOWED)}: {top}"
                        )


class TestStorageDriverLaziness(unittest.TestCase):
    """Storage DB drivers must load only when a backend is used."""

    def _modules_loaded_by(self, stmt: str) -> set[str]:
        result = subprocess.run(
            [sys.executable, "-c", stmt],
            capture_output=True,
            text=True,
            check=True,
        )
        return set(result.stdout.strip().split(","))

    def test_import_storage_does_not_load_drivers(self):
        """Test that importing campus.storage loads no database driver."""
        loaded = self._modules_loaded_by(
            "import campus.storage, sys; print(','.join(sorted(sys.modules)))"
        )
        for driver in ("psycopg2", "pymongo", "boto3", "botocore"):
            self.assertNotIn(driver, loaded)
