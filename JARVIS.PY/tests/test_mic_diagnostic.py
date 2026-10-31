"""Diagnostic CLI coverage with mocked hardware and synthetic device errors."""

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "mic_diagnostic", Path(__file__).resolve().parents[1] / "mic_test.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class MicrophoneDiagnosticTests(unittest.TestCase):
    def test_default_and_custom_settings_preserve_bounded_capture(self):
        for args, expected in (([], (1, 44100, 1024)),
                               (["--device-index", "0", "--sample-rate", "16000",
                                 "--chunk-size", "512"], (0, 16000, 512))):
            with patch.object(diagnostic.sr, "Microphone") as mic, \
                    patch.object(diagnostic.sr, "Recognizer") as recognizer, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(diagnostic.cli(args), 0)
                mic.assert_called_once_with(device_index=expected[0], sample_rate=expected[1],
                                            chunk_size=expected[2])
                recognizer.return_value.listen.assert_called_once_with(
                    mic.return_value.__enter__.return_value, timeout=5, phrase_time_limit=3)
                self.assertIn("Audio captured successfully", output.getvalue())

    def test_invalid_settings_do_not_open_microphone(self):
        for args in (["--device-index", "-1"], ["--sample-rate", "0"], ["--chunk-size", "bad"]):
            with patch.object(diagnostic.sr, "Microphone") as mic, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    diagnostic.cli(args)
                self.assertEqual(caught.exception.code, 2)
                mic.assert_not_called()

    def test_timeouts_and_device_errors_have_safe_failure_status(self):
        for error in (diagnostic.sr.WaitTimeoutError(), OSError("synthetic private device detail")):
            with patch.object(diagnostic.sr, "Microphone") as mic, \
                    patch.object(diagnostic.sr, "Recognizer") as recognizer, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                recognizer.return_value.listen.side_effect = error
                self.assertEqual(diagnostic.main(), 1)
                mic.return_value.__exit__.assert_called_once()
                self.assertNotIn("synthetic private device detail", output.getvalue())
                self.assertNotIn("Audio captured successfully", output.getvalue())

    def test_help_never_opens_hardware(self):
        with patch.object(diagnostic.sr, "Microphone") as mic, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                diagnostic.cli(["--help"])
            self.assertEqual(caught.exception.code, 0)
            mic.assert_not_called()
