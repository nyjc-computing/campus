"""Drift test: docs/required-env-vars.md must match the generator (#1108).

Same shape as the OpenAPI drift tests: the matrix is RENDERED from
campus.bootstrap.REQUIRED_ENV_VARS (the declarations main.create_app
enforces at boot), so a declaration change without re-running
scripts/generate_required_vars_doc.py fails here.
"""

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "required-env-vars.md"
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_required_vars_doc.py"


class TestRequiredEnvVarsDoc(unittest.TestCase):

    def load_render(self) -> str:
        spec = importlib.util.spec_from_file_location(
            "generate_required_vars_doc", GENERATOR_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.render()

    def test_committed_doc_matches_generator(self):
        self.assertTrue(DOC_PATH.is_file(),
                        "docs/required-env-vars.md missing — run "
                        "scripts/generate_required_vars_doc.py")
        committed = DOC_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            committed, self.load_render(),
            "docs/required-env-vars.md drifted from "
            "campus.bootstrap.REQUIRED_ENV_VARS — re-run "
            "scripts/generate_required_vars_doc.py",
        )

    def test_every_service_declares_a_matrix(self):
        from campus import bootstrap
        self.assertEqual(
            set(bootstrap.REQUIRED_ENV_VARS),
            {"campus.auth", "campus.api", "campus.audit"},
        )
        for mode, required in bootstrap.REQUIRED_ENV_VARS.items():
            self.assertTrue(required, f"{mode} declares nothing")


if __name__ == "__main__":
    unittest.main()
