"""Exercise the real CLI in isolated processes with all external actions blocked."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


GUARDED_CLI = """
import http.client, os, runpy, smtplib, sys, webbrowser
import pyttsx3, speech_recognition as sr
def blocked(*args, **kwargs):
    raise AssertionError('External action forbidden in CLI regression')
sr.Microphone = blocked
sr.Recognizer.recognize_google = blocked
pyttsx3.init = blocked
smtplib.SMTP = blocked
http.client.HTTPSConnection = blocked
webbrowser.open = blocked
os.startfile = blocked
script = sys.argv[1]
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name='__main__')
"""


class CLIProcessTests(unittest.TestCase):
    def run_cli(self, args, text=""):
        script = Path(__file__).resolve().parents[1] / "JARVIS2.0.py"
        # Allowlist essentials instead of passing any user credential environment.
        env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP")
               if name in os.environ}
        env.update(JARVIS_AI_PROVIDER="disabled", PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, "-B", "-c", GUARDED_CLI, str(script), *args],
                                input=text, text=True, encoding="utf-8", capture_output=True,
                                env=env, timeout=20)
        self.assertEqual(result.returncode, 0, "CLI failed; captured output omitted")
        self.assertNotIn("External action forbidden", result.stdout + result.stderr)
        return result.stdout

    def test_help_starts_without_devices_or_services(self):
        self.assertIn("--text", self.run_cli(["--help"]))

    def test_eof_shuts_down_cleanly(self):
        self.assertIn("Jarvis stopped.", self.run_cli(["--text", "--no-tts"]))

    def test_local_commands_reset_dry_runs_and_quit(self):
        output = self.run_cli(["--text", "--no-tts"],
                              "help\nclear conversation\ntime\nopen google\nemail to raj\nquit\n")
        for expected in ("Try time", "Local conversation history cleared", "Sir, the time is",
                         "Dry run: google", "Dry run: email", "Goodbye"):
            self.assertIn(expected, output)
