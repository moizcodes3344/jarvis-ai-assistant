"""Batch three regressions: synthetic data and blocked external services only."""

import contextlib
import io
import os
import unittest
from unittest.mock import MagicMock, patch

from test_stable_core import jarvis


class SMTPResponseTests(unittest.TestCase):
    def test_acceptance_is_preserved_after_quit_failure(self):
        for cleanup_error in (None, jarvis.smtplib.SMTPResponseException(500, b"synthetic detail")):
            with patch.dict(os.environ, {"JARVIS_EMAIL_ADDRESS": "sender@example.com",
                                        "JARVIS_EMAIL_PASSWORD": "synthetic-password"}, clear=True), \
                    patch.object(jarvis.smtplib, "SMTP") as smtp:
                server = smtp.return_value.__enter__.return_value
                server.ehlo.return_value = (250, b"ok")
                smtp.return_value.__exit__.side_effect = cleanup_error
                expected = "accepted_cleanup_failed" if cleanup_error else "accepted"
                self.assertEqual(jarvis.sendEmail("recipient@example.com", "body"), expected)
                server.sendmail.assert_called_once()
        with patch.dict(os.environ, {"JARVIS_EMAIL_ADDRESS": "sender@example.com",
                                    "JARVIS_EMAIL_PASSWORD": "synthetic-password"}, clear=True), \
                patch.object(jarvis.smtplib, "SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            server.ehlo.return_value = (250, b"ok")
            server.sendmail.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                jarvis.sendEmail("recipient@example.com", "body")
            server.sendmail.assert_called_once()

    def test_returned_greeting_errors_stop_authentication(self):
        for replies in ([(550, b"synthetic refusal")],
                        [(250, b"ok"), (421, b"synthetic refusal")]):
            with patch.dict(os.environ, {"JARVIS_EMAIL_ADDRESS": "sender@example.com",
                                        "JARVIS_EMAIL_PASSWORD": "synthetic-password"}, clear=True), \
                    patch.object(jarvis.smtplib, "SMTP") as smtp:
                server = smtp.return_value.__enter__.return_value
                server.ehlo.side_effect = replies
                with self.assertRaises(jarvis.smtplib.SMTPHeloError) as caught:
                    jarvis.sendEmail("recipient@example.com", "body")
                self.assertNotIn("synthetic refusal", str(caught.exception))
                server.login.assert_not_called()
                server.sendmail.assert_not_called()
                if len(replies) == 1:
                    server.starttls.assert_not_called()


class NegationTests(unittest.TestCase):
    def test_negated_or_mixed_actions_remain_local_without_side_effects(self):
        phrases = ("don't open google", "do not play music", "never open code",
                   "do not email to raj", "don't launch youtube", "can you not open stack overflow",
                   "please don't search wikipedia cats", "do not clear conversation",
                   "don't quit", "open google but do not play music")
        with patch.object(jarvis, "speak"), patch.object(jarvis.webbrowser, "open") as browser, \
                patch.object(jarvis.os, "startfile", create=True) as launch, \
                patch.object(jarvis, "sendEmail") as email, \
                patch.object(jarvis, "search_wikipedia") as wikipedia:
            for phrase in phrases:
                ai = MagicMock()
                self.assertEqual(jarvis.command_for(phrase), "negated_action")
                self.assertTrue(jarvis.handle_command(phrase, ai=ai))
                ai.reply.assert_not_called()
                ai.clear.assert_not_called()
            for action in (browser, launch, email, wikipedia):
                action.assert_not_called()

    def test_positive_commands_and_unrelated_negation_preserved(self):
        for phrase, command in (("open google", "google"), ("play music", "music"),
                                ("open code", "code"), ("email to raj", "email"),
                                ("open google for not found errors", "google"),
                                ("wikipedia Never Gonna Give You Up", "wikipedia")):
            self.assertEqual(jarvis.command_for(phrase), command)
        self.assertIsNone(jarvis.command_for("explain why I should not worry"))


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
