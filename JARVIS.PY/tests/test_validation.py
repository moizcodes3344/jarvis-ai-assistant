"""Regression tests for publication checks; never use live credentials."""

import importlib.util
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "validation", Path(__file__).resolve().parents[1] / "tools" / "validate.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class ValidationTests(unittest.TestCase):
    def test_repository_failures_are_redacted_and_fail_closed(self):
        errors = (FileNotFoundError("synthetic private detail"),
                  subprocess.CalledProcessError(1, ["synthetic private detail"],
                                                stderr=b"synthetic private detail"),
                  subprocess.TimeoutExpired("synthetic private detail", 30))
        for error in errors:
            with patch.object(validation, "git_bytes", side_effect=error), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(validation.main([]), 1)
                self.assertNotIn("synthetic private detail", output.getvalue())
                self.assertIn("validation failed", output.getvalue())

    def test_unreadable_file_has_redacted_diagnostic(self):
        with patch.object(Path, "read_bytes", side_effect=PermissionError("synthetic detail")):
            self.assertEqual(validation.check_file(Path("sample.py"), "sample.py"),
                             [("sample.py", 1, "file unavailable for validation")])

    def test_staged_scan_reads_index_not_working_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "--quiet", directory], check=True, capture_output=True)
            path = root / "sample.py"
            synthetic = "sk-" + "aB3d" * 10
            for staged, disk, expected_index, expected_disk in (
                (f'VALUE = "{synthetic}"\n', 'VALUE = "safe"\n', 1, 0),
                ('VALUE = "safe"\n', f'VALUE = "{synthetic}"\n', 0, 1),
            ):
                path.write_text(staged, encoding="utf-8")
                subprocess.run(["git", "add", "--", "sample.py"], cwd=root,
                               check=True, capture_output=True)
                path.write_text(disk, encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(validation.main(["--staged"], root), expected_index)
                    self.assertEqual(validation.main([], root), expected_disk)
                self.assertNotIn(synthetic, output.getvalue())

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
