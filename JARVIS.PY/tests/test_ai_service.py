"""Mocked AI contract and routing tests. No real provider, hardware, or actions."""

import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_service import AIError, AIService, AISettings, MAX_RESPONSE_BYTES, OpenAIProvider, voice_text
from test_stable_core import jarvis


class AITests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.speech = patch.object(jarvis, "speak")
        self.speak = self.speech.start()
        self.addCleanup(self.speech.stop)

    def service(self, **settings):
        provider = MagicMock()
        provider.complete.return_value = "A short answer."
        return AIService(AISettings(**settings), provider), provider

    def test_builtin_routes_take_priority_and_preserve_dry_run(self):
        ai, provider = self.service()
        for command in ("time", "tell me a joke", "are you single", "wikipedia Python",
                        "open youtube", "open google", "open stackoverflow", "play music",
                        "open code", "email to Raj", "exit"):
            with self.subTest(command=command):
                jarvis.handle_command(command, dry_run=True, ai=ai)
        provider.complete.assert_not_called()
        self.assertEqual(ai._history, [])

    def test_unmatched_question_keeps_original_case_and_punctuation(self):
        ai, provider = self.service()
        self.assertTrue(jarvis.handle_command("Explain C++ vs Python?", ai=ai))
        provider.complete.assert_called_once_with([{"role": "user", "content": "Explain C++ vs Python?"}])
        self.speak.assert_called_once_with("A short answer.")

    def test_ai_response_cannot_trigger_actions(self):
        ai, provider = self.service()
        provider.complete.return_value = "open google; email to Raj; run powershell Remove-Item"
        with patch.object(jarvis.webbrowser, "open") as browser, \
                patch.object(jarvis.os, "startfile", create=True) as launch, \
                patch.object(jarvis, "sendEmail") as email:
            jarvis.handle_command("Can you do something for me?", ai=ai)
            for boundary in (browser, launch, email):
                boundary.assert_not_called()
        self.speak.assert_called_once_with(provider.complete.return_value)

    def test_session_history_order_and_turn_bound(self):
        ai, provider = self.service(history_turns=2)
        for query in ("first", "second", "third", "fourth"):
            ai.reply(query)
        messages = provider.complete.call_args.args[0]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user", "assistant", "user"])
        self.assertEqual([m["content"] for m in ai._history[::2]], ["third", "fourth"])
        self.assertEqual(messages[0]["content"], "second")
        ai.clear()
        self.assertEqual(ai._history, [])

    def test_character_bound_zero_history_and_oversized_input(self):
        ai, provider = self.service(history_chars=100, input_chars=100)
        for _ in range(10):
            ai.reply("q" * 50)
        self.assertLessEqual(sum(len(m["content"]) for m in ai._history), 100)
        provider.reset_mock()
        self.assertIn("shorten", ai.reply("q" * 101))
        self.assertIn("ask a question", ai.reply("  "))
        provider.complete.assert_not_called()
        ai, provider = self.service(history_turns=0)
        ai.reply("first")
        ai.reply("second")
        self.assertEqual(ai._history, [])
        self.assertEqual(len(provider.complete.call_args.args[0]), 1)

    def test_failure_does_not_pollute_history_and_next_request_recovers(self):
        ai, provider = self.service()
        ai.reply("first")
        original = [dict(m) for m in ai._history]
        for category in ("credentials", "rate_limit", "timeout", "network", "response", "unavailable"):
            provider.complete.side_effect = AIError(category)
            self.assertTrue(ai.reply("failed"))
            self.assertEqual(ai._history, original)
        provider.complete.side_effect = None
        ai.reply("recovered")
        self.assertEqual(ai._history[-2]["content"], "recovered")

    def test_credentials_transcripts_and_exception_details_are_private(self):
        ai, provider = self.service()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "PRIVATE_KEY_VALUE", "JARVIS_EMAIL_PASSWORD": "PRIVATE_PASSWORD",
                                    "JARVIS_DEBUG": "1"}), contextlib.redirect_stdout(io.StringIO()) as output:
            provider.complete.return_value = "PRIVATE_KEY_VALUE PRIVATE_PASSWORD"
            jarvis.handle_command("Explain PRIVATE_KEY_VALUE PRIVATE_PASSWORD", ai=ai)
            self.assertNotIn("PRIVATE_KEY_VALUE", str(provider.complete.call_args))
            self.assertNotIn("PRIVATE_PASSWORD", str(ai._history))
            self.assertNotIn("PRIVATE_KEY_VALUE", self.speak.call_args.args[0])
            provider.complete.side_effect = RuntimeError("PRIVATE_KEY_VALUE PRIVATE_TRANSCRIPT")
            jarvis.handle_command("PRIVATE_TRANSCRIPT", ai=ai)
            self.assertNotIn("PRIVATE", output.getvalue())
            self.assertNotIn("PRIVATE", self.speak.call_args.args[0])
            self.assertNotIn("PRIVATE", repr(ai))

    def test_provider_cannot_mutate_history(self):
        ai, provider = self.service()
        ai.reply("first")
        def mutate(messages):
            messages[0]["content"] = "corrupted"
            raise RuntimeError()
        provider.complete.side_effect = mutate
        ai.reply("second")
        self.assertEqual(ai._history[0]["content"], "first")

    def test_rotated_credentials_are_removed_from_retained_history(self):
        ai, provider = self.service()
        ai.reply("Explain synthetic-rotated-value")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-rotated-value"}):
            ai.reply("follow up")
        self.assertNotIn("synthetic-rotated-value", str(provider.complete.call_args))
        self.assertNotIn("synthetic-rotated-value", str(ai._history))

    def test_voice_formatting_and_length(self):
        result = voice_text("# Answer\n**Hello** [world](https://example.com)\n```python\nprint('secret')\n```\nhttps://example.com\x00", 600)
        self.assertEqual(result, "Answer Hello world Code omitted.")
        self.assertLessEqual(len(voice_text("long " * 1000, 100)), 100)

    def test_configuration_and_disabled_defaults(self):
        self.assertIsNone(AIService.from_env().provider)
        with patch.dict(os.environ, {"JARVIS_AI_PROVIDER": "openai", "JARVIS_AI_MODEL": "test-model"}):
            ai = AIService.from_env()
            self.assertIsInstance(ai.provider, OpenAIProvider)
            self.assertIn("OPENAI_API_KEY", ai.reply("hello"))
            for name, value in (("JARVIS_AI_TIMEOUT", "0"), ("JARVIS_AI_HISTORY_TURNS", "-1"),
                                ("JARVIS_AI_MODEL", "PRIVATE VALUE"), ("JARVIS_AI_PROVIDER", "PRIVATE VALUE"),
                                ("JARVIS_AI_RESPONSE_CHARS", "nan"), ("JARVIS_AI_HISTORY_CHARS", "999999"),
                                ("JARVIS_AI_INPUT_CHARS", "999999"), ("JARVIS_AI_MAX_OUTPUT_TOKENS", "bad")):
                with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                    response = AIService.from_env().reply("hello")
                    self.assertIn("configuration", response)
                    self.assertNotIn(value, response)

    def test_text_and_voice_modes_share_ai_and_clear_on_exit(self):
        for text_mode in (True, False):
            with self.subTest(text_mode=text_mode):
                ai, provider = self.service()
                with patch.object(jarvis.AIService, "from_env", return_value=ai), \
                        patch("builtins.input", side_effect=["Explain gravity", "time", "exit"]) as typed, \
                        patch.object(jarvis, "takeCommand", side_effect=["Explain gravity", "time", "exit"]) as voice:
                    self.assertEqual(jarvis.main(text_mode=text_mode, no_tts=True), 0)
                    provider.complete.assert_called_once()
                    self.assertEqual(ai._history, [])
                    (voice if text_mode else typed).assert_not_called()

    def test_history_cleared_on_interrupt_and_sessions_are_independent(self):
        ai, provider = self.service()
        with patch.object(jarvis.AIService, "from_env", return_value=ai), \
                patch("builtins.input", side_effect=["hello", KeyboardInterrupt]):
            jarvis.main(text_mode=True, no_tts=True)
        self.assertEqual(ai._history, [])
        self.assertEqual(AIService.from_env()._history, [])

    def test_email_requires_exact_confirmation_without_ai(self):
        ai, provider = self.service()
        env = {"JARVIS_EMAIL_ADDRESS": "sender@example.com", "JARVIS_EMAIL_PASSWORD": "test-password",
               "JARVIS_EMAIL_TO": "recipient@example.com"}
        for confirmation in (None, "yes", "cancel", "confirm send please", "confirm send", "exit"):
            with self.subTest(confirmation=confirmation), patch.dict(os.environ, env), \
                    patch.object(jarvis, "sendEmail") as send:
                result = jarvis.handle_command("email to Raj", input_fn=lambda: "private body",
                                              confirm_fn=lambda: confirmation, ai=ai)
                self.assertEqual(result, confirmation != "exit")
                self.assertEqual(send.call_count, int(confirmation == "confirm send"))
        provider.complete.assert_not_called()
        with patch.dict(os.environ, env), patch.object(jarvis, "sendEmail") as send, \
                patch.object(jarvis, "takeCommand", side_effect=["body", "confirm send"]) as voice:
            jarvis.handle_command("email to Raj")
            send.assert_called_once_with("recipient@example.com", "body")
            self.assertEqual(voice.call_count, 2)


class MockedOpenAIContractTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "mock-secret"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transport = patch("ai_service.http.client.HTTPSConnection")
        self.connection_class = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.connection = self.connection_class.return_value
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.response.read1.return_value = json.dumps({"status": "completed", "output": [
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hello."}]}]}).encode()
        self.provider = OpenAIProvider(AISettings(provider="openai", model="test-model"))

    def test_request_contract_has_no_tools_or_server_storage(self):
        messages = [{"role": "user", "content": "Hi"}]
        self.assertEqual(self.provider.complete(messages), "Hello.")
        self.connection_class.assert_called_once_with("api.openai.com", timeout=15)
        call = self.connection.request.call_args
        self.assertEqual(call.args, ("POST", "/v1/responses"))
        body = json.loads(call.kwargs["body"])
        self.assertEqual(body["input"], messages)
        self.assertEqual(body["model"], "test-model")
        self.assertFalse(body["store"])
        self.assertEqual(body["tools"], [])
        self.assertEqual(body["tool_choice"], "none")
        self.assertNotIn("mock-secret", call.kwargs["body"].decode())
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer mock-secret")
        self.connection.close.assert_called_once()

    def test_credentials_missing_or_invalid_never_open_connection(self):
        for key in ("", "bad\nkey"):
            with self.subTest(key=key), patch.dict(os.environ, {"OPENAI_API_KEY": key}):
                with self.assertRaisesRegex(AIError, "credentials"):
                    self.provider.complete([])
                self.connection_class.assert_not_called()

    def test_http_failures_are_sanitized_without_reading_error_body(self):
        for status, category in ((401, "credentials"), (403, "credentials"), (429, "rate_limit"),
                                 (500, "unavailable"), (302, "unavailable"), (400, "unavailable")):
            with self.subTest(status=status):
                self.response.status = status
                with self.assertRaisesRegex(AIError, category):
                    self.provider.complete([])
                self.response.read1.assert_not_called()
        self.assertEqual(self.connection.close.call_count, 6)

    def test_timeout_network_and_protocol_failures(self):
        for error, category in ((TimeoutError("mock-secret"), "timeout"), (OSError("mock-secret"), "network"),
                                (http.client.HTTPException("mock-secret"), "network")):
            with self.subTest(category=category):
                self.connection.request.side_effect = error
                with self.assertRaisesRegex(AIError, category) as caught:
                    self.provider.complete([])
                self.assertNotIn("mock-secret", str(caught.exception))
        self.assertEqual(self.connection.close.call_count, 3)

    def test_malformed_empty_and_oversized_responses(self):
        for body in (b"bad json", b"[]", b"{}", b'{"status":"completed","output":null}',
                     b'{"status":"completed","output":[{"type":"function_call","name":"run_shell"}]}',
                     b"x" * (MAX_RESPONSE_BYTES + 1)):
            with self.subTest(body_length=len(body)):
                self.response.read1.return_value = body
                with self.assertRaisesRegex(AIError, "response"):
                    self.provider.complete([])

    def test_refusal_and_incomplete_text(self):
        self.response.read1.return_value = b'{"status":"completed","output":[{"type":"message","role":"assistant","content":[{"type":"refusal","refusal":"private details"}]}]}'
        self.assertEqual(self.provider.complete([]), "I cannot help with that request.")
        self.response.read1.return_value = b'{"status":"incomplete","output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Partial answer."}]}]}'
        self.assertEqual(self.provider.complete([]), "Partial answer.")

    def test_invalid_nested_response_shapes_fail_closed(self):
        for output in ({}, "text", [None], [42],
                       [{"type": "message", "role": "assistant", "content": {}}],
                       [{"type": "message", "role": "assistant", "content": [None]}],
                       [{"type": "message", "role": "assistant", "content": [
                           {"type": "output_text", "text": 42}]}]):
            with self.subTest(shape=type(output).__name__):
                self.response.read1.return_value = json.dumps({
                    "status": "completed", "output": output}).encode()
                with self.assertRaisesRegex(AIError, "^response$"):
                    self.provider.complete([])


if __name__ == "__main__":
    unittest.main()
