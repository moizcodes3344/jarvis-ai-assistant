"""Regression tests for publication checks; never use live credentials."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "validation", Path(__file__).resolve().parents[1] / "tools" / "validate.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class ValidationTests(unittest.TestCase):
    def check(self, text, name="sample.py"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / Path(name).name
            path.write_text(text, encoding="utf-8")
            return validation.check_file(path, name)

    def test_secret_detection_never_returns_the_value(self):
        synthetic = "sk-" + "aB3d" * 10
        issues = self.check(f'VALUE = "{synthetic}"\n')
        self.assertEqual(issues, [("sample.py", 1, "credential pattern")])
        self.assertNotIn(synthetic, str(issues))

    def test_syntax_and_formatting_diagnostics_are_redacted(self):
        issues = self.check("def broken(  \n")
        self.assertEqual({i[2] for i in issues}, {"trailing whitespace", "Python syntax error"})

    def test_private_paths_fail_even_without_secret_signatures(self):
        for name in (".env", "local/.env.production", ".venv/activate.py", "private.pem"):
            with self.subTest(name=name):
                self.assertTrue(self.check("", name))

    def test_placeholder_example_and_valid_python_pass(self):
        self.assertEqual(self.check("OPENAI_API_KEY=\n", ".env.example"), [])
        self.assertEqual(self.check('print("safe")\n'), [])
