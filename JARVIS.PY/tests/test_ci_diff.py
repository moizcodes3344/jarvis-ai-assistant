"""Cover PR, normal push, new-branch and manual whitespace scopes."""

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "ci_diff", Path(__file__).resolve().parents[1] / "tools" / "check_diff.py")
ci_diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_diff)


class DiffScopeTests(unittest.TestCase):
    def test_event_ranges(self):
        base, head = "a" * 40, "b" * 40
        self.assertEqual(ci_diff.changed_range("push", {"before": base, "after": head}), base + ".." + head)
        self.assertEqual(ci_diff.changed_range("push", {"before": "0" * 40, "after": head}),
                         "origin/main..." + head)
        self.assertEqual(ci_diff.changed_range("pull_request", {"pull_request": {
            "base": {"sha": base}, "head": {"sha": head}}}), base + "..." + head)
        self.assertEqual(ci_diff.changed_range("workflow_dispatch", {}), "origin/main...HEAD")

    def test_invalid_event_revisions_fail_closed(self):
        for value in (None, "--help", "a; echo unsafe", "a" * 39):
            with self.assertRaises(ValueError):
                ci_diff.changed_range("push", {"before": "a" * 40, "after": value})

    def test_git_failures_do_not_print_source(self):
        with patch.dict(ci_diff.os.environ, {"GITHUB_EVENT_PATH": "synthetic.json",
                                           "GITHUB_EVENT_NAME": "workflow_dispatch"}, clear=True), \
                patch.object(Path, "read_text", return_value="{}"), \
                patch.object(ci_diff.subprocess, "run", return_value=MagicMock(
                    returncode=2, stdout=b"synthetic private source")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ci_diff.main(), 1)
            self.assertNotIn("synthetic private source", output.getvalue())
