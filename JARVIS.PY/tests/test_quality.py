"""Focused quality regressions; external actions and hardware are mocked."""

import contextlib
import io
import os
import unittest
from unittest.mock import patch

from test_stable_core import jarvis


class EmailValidationTests(unittest.TestCase):
    def test_invalid_envelope_never_connects_or_echoes_configuration(self):
        for mailbox in ("bad\r\nRCPT TO: other@example.com", "a@example.com,b@example.com",
                        "display <a@example.com>", "missing-at", "a@", "é@example.com"):
            for field in ("sender", "recipient"):
                with self.subTest(field=field), patch.dict(os.environ, {
                    "JARVIS_EMAIL_ADDRESS": mailbox if field == "sender" else "a@example.com",
                    "JARVIS_EMAIL_PASSWORD": "synthetic-password",
                }, clear=True), patch.object(jarvis.smtplib, "SMTP") as smtp:
                    with self.assertRaisesRegex(ValueError, "^Email address configuration is invalid$"):
                        jarvis.sendEmail(mailbox if field == "recipient" else "b@example.com", "body")
                    smtp.assert_not_called()

    def test_blank_message_cancels_without_confirmation(self):
        for content in (None, "", " \t\n"):
            with self.subTest(content=content), patch.dict(os.environ, {
                "JARVIS_EMAIL_ADDRESS": "a@example.com",
                "JARVIS_EMAIL_TO": "b@example.com",
                "JARVIS_EMAIL_PASSWORD": "synthetic-password",
            }, clear=True), patch.object(jarvis, "speak"), \
                    patch.object(jarvis, "sendEmail") as send, \
                    patch.object(jarvis, "takeCommand") as confirm:
                self.assertTrue(jarvis.handle_command("email to raj", input_fn=lambda: content))
                confirm.assert_not_called()
                send.assert_not_called()
