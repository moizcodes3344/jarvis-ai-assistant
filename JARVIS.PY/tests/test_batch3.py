"""Batch three regressions: synthetic data and blocked external services only."""

import contextlib
import io
import os
import unittest
from unittest.mock import MagicMock, patch

from test_stable_core import jarvis


class VoiceSecurityTests(unittest.TestCase):
    def setUp(self):
        calibration = patch.object(jarvis.Listener, "adjust_for_ambient_noise")
        calibration.start()
        self.addCleanup(calibration.stop)

    def test_https_endpoint_language_and_timeout_preserved(self):
        with patch.dict(os.environ, {"JARVIS_RECOGNITION_LANGUAGE": "ur-PK",
                                    "JARVIS_RECOGNITION_TIMEOUT": "12"}, clear=True), \
                patch.object(jarvis.sr, "Microphone"), patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="time") as recognize, \
                patch.object(jarvis.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(jarvis.takeCommand(), "time")
            self.assertEqual(recognize.call_args.kwargs, {
                "language": "ur-PK", "endpoint": jarvis.GOOGLE_RECOGNITION_ENDPOINT})
            self.assertTrue(jarvis.GOOGLE_RECOGNITION_ENDPOINT.startswith("https://"))
            self.assertEqual(jarvis.Listener.operation_timeout, 12)

    def test_https_service_failure_never_retries_with_http(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", side_effect=jarvis.sr.RequestError(
                    "synthetic endpoint failure")) as recognize, \
                patch.object(jarvis.time, "sleep"), patch.object(jarvis, "speak"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertIsNone(jarvis.takeCommand())
            recognize.assert_called_once()
            self.assertTrue(recognize.call_args.kwargs["endpoint"].startswith("https://"))
            self.assertNotIn("synthetic endpoint failure", output.getvalue())
