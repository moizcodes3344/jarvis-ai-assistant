"""Batch two regressions use synthetic configuration and mocked transports."""

import contextlib
from email import policy
from email.parser import BytesParser
import io
import os
import unittest
from unittest.mock import MagicMock, patch

from test_stable_core import jarvis


EMAIL_ENV = {
    "JARVIS_EMAIL_ADDRESS": "sender@example.com",
    "JARVIS_EMAIL_TO": "recipient@example.com",
    "JARVIS_EMAIL_PASSWORD": "synthetic-password",
}


class EmailTests(unittest.TestCase):
    def test_unicode_message_round_trips_through_ascii_safe_mime(self):
        for body in ("Hello", "السلام علیکم\nUrdu and emoji: 🌟"):
            with self.subTest(body_type=type(body).__name__), \
                    patch.dict(os.environ, EMAIL_ENV, clear=True), \
                    patch.object(jarvis.smtplib, "SMTP") as smtp:
                jarvis.sendEmail("recipient@example.com", body)
                call = smtp.return_value.__enter__.return_value.sendmail.call_args
                self.assertEqual(call.args[:2], ("sender@example.com", "recipient@example.com"))
                wire = call.args[2]
                wire.decode("ascii")
                message = BytesParser(policy=policy.default).parsebytes(wire)
                self.assertEqual(message.get_content().replace("\r\n", "\n"), body + "\n")
                self.assertEqual(message["To"], "recipient@example.com")
