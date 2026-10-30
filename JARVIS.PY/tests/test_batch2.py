"""Batch two regressions use synthetic configuration and mocked transports."""

import contextlib
from email import policy
from email.parser import BytesParser
import io
import json
import os
import unittest
import warnings
from unittest.mock import MagicMock, patch

from test_stable_core import jarvis


EMAIL_ENV = {
    "JARVIS_EMAIL_ADDRESS": "sender@example.com",
    "JARVIS_EMAIL_TO": "recipient@example.com",
    "JARVIS_EMAIL_PASSWORD": "synthetic-password",
}


class ProviderCleanupTests(unittest.TestCase):
    def test_close_failures_preserve_primary_errors_and_success(self):
        from ai_service import AIError, AISettings, GeminiProvider, OpenAIProvider

        for provider_type in (OpenAIProvider, GeminiProvider):
            for status in (200, 401, 429):
                with self.subTest(provider=provider_type.__name__, status=status), \
                        patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-openai",
                                                "GEMINI_API_KEY": "synthetic-gemini"}, clear=True), \
                        patch("ai_service.http.client.HTTPSConnection") as transport:
                    connection = transport.return_value
                    connection.close.side_effect = OSError("synthetic private detail")
                    response = connection.getresponse.return_value
                    response.status = status
                    response.read.return_value = json.dumps({
                        "status": "completed", "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": "Hello"}]}],
                        "choices": [{"message": {"role": "assistant", "content": "Hello"}}],
                    }).encode()
                    provider = provider_type(AISettings())
                    if status == 200:
                        self.assertEqual(provider.complete([]), "Hello")
                    else:
                        with self.assertRaisesRegex(AIError, "^credentials$" if status == 401 else "^rate_limit$"):
                            provider.complete([])
                    connection.close.assert_called_once()


class OutputTests(unittest.TestCase):
    def test_terminal_sequences_removed_without_losing_unicode(self):
        from ai_service import safe_output_text, voice_text

        unsafe = "\x1b[31mسلام\x1b[0m\x1b]0;title\x07\r\b\x00\x9b2J 🌟\u202e"
        self.assertEqual(safe_output_text(unsafe), "سلام 🌟")
        with patch.object(jarvis, "speech_enabled", False), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.speak(unsafe)
        self.assertEqual(output.getvalue(), "Jarvis: سلام 🌟\n")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-value"}, clear=True):
            split = "synthetic-\x1b[31mvalue"
            self.assertEqual(safe_output_text(split), "[credential omitted]")
            self.assertNotIn("synthetic-value", voice_text(split, 600))

    def test_wikipedia_summary_is_redacted_before_console_and_speech(self):
        synthetic = "synthetic-wiki-credential"
        with patch.dict(os.environ, {"GEMINI_API_KEY": synthetic}, clear=True), \
                patch.object(jarvis.wikipedia, "summary", return_value="Answer " + synthetic), \
                patch.object(jarvis, "speech_enabled", False), \
                patch.object(jarvis, "speak", wraps=jarvis.speak) as speak, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.search_wikipedia("wikipedia topic")
            self.assertNotIn(synthetic, output.getvalue())
            self.assertNotIn(synthetic, str(speak.call_args_list))
            self.assertIn("Answer [credential omitted]", output.getvalue())


class EmailTests(unittest.TestCase):
    def test_hidden_input_warning_prevents_visible_fallback(self):
        fallback = MagicMock()

        def unavailable(prompt):
            warnings.warn("synthetic private detail", jarvis.getpass.GetPassWarning)
            return fallback()

        with patch.object(jarvis.getpass, "getpass", side_effect=unavailable), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertIsNone(jarvis.read_email_message())
            fallback.assert_not_called()
            self.assertNotIn("synthetic private detail", output.getvalue())
        for error in (EOFError(), OSError("synthetic private detail")):
            with patch.object(jarvis.getpass, "getpass", side_effect=error), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(jarvis.read_email_message())
        with patch.object(jarvis.getpass, "getpass", return_value="body"):
            self.assertEqual(jarvis.read_email_message(), "body")

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
