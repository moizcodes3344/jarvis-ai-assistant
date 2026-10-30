"""Scanner result handling is tested without contacting advisory services."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).resolve().parents[1] / "tools" / "audit_dependencies.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def result(self, dependencies, code):
        return MagicMock(returncode=code, stdout=json.dumps({"dependencies": dependencies}).encode())

    def test_safe_and_vulnerable_reports(self):
        for vulns, code, expected in (([], 0, 0), ([{"id": "SYNTHETIC-1"}], 1, 1)):
            with patch.object(audit.subprocess, "run", return_value=self.result([
                {"name": "synthetic-package", "version": "1.0", "vulns": vulns}], code)) as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit.audit_paths(["synthetic-site"]), expected)
                command = run.call_args.args[0]
                self.assertNotIn("--fix", command)
                self.assertNotIn("--ignore-vuln", command)
                self.assertIn("--strict", command)

    def test_outage_empty_or_skipped_reports_fail_closed(self):
        reports = (MagicMock(returncode=1, stdout=b"synthetic private detail"),
                   self.result([], 0), self.result([{"skip_reason": "synthetic detail"}], 0))
        for result in reports:
            with patch.object(audit.subprocess, "run", return_value=result), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(audit.audit_paths(["synthetic-site"]), 2)
                self.assertIn("ERROR", output.getvalue())
                self.assertNotIn("synthetic", output.getvalue())
        with patch.object(audit.subprocess, "run", side_effect=subprocess.TimeoutExpired("scanner", 180)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.audit_paths(["synthetic-site"]), 2)
