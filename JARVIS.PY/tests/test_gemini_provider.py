"""Gemini transport/integration checks with synthetic keys; no live API calls."""

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
from ai_service import AIError, AIService, AISettings, GeminiProvider, INSTRUCTIONS, MAX_RESPONSE_BYTES, OpenAIProvider, redact_credentials, voice_text
from test_stable_core import jarvis


class GeminiProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "JARVIS_AI_PROVIDER": "gemini", "JARVIS_AI_MODEL": "gemini-3.8-flash",
            "GEMINI_API_KEY": "GeminiSyntheticCredential123", "OPENAI_API_KEY": "OpenAISyntheticCredential456",
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transport = patch("ai_service.http.client.HTTPSConnection")
        self.connection_class = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.connection = self.connection_class.return_value
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.response.read1.return_value = self.response_body("A concise answer.")
        self.service = AIService.from_env()
        self.provider = self.service.provider

    @staticmethod
    def response_body(content, **message_fields):
        return json.dumps({"choices": [{"message": {
            "role": "assistant", "content": content, **message_fields,
        }, "finish_reason": "stop"}]}).encode()

    def test_factory_preserves_all_provider_modes_and_model_selection(self):
        self.assertIsInstance(self.provider, GeminiProvider)
        self.assertEqual(self.service.settings.model, "gemini-3.8-flash")
        self.assertEqual(self.service.settings.max_output_tokens, 1024)
        with patch.dict(os.environ, {"JARVIS_AI_MODEL": "another-model", "JARVIS_AI_MAX_OUTPUT_TOKENS": "512"}):
            self.assertEqual(AIService.from_env().settings.model, "another-model")
            self.assertEqual(AIService.from_env().settings.max_output_tokens, 512)
        with patch.dict(os.environ, {"JARVIS_AI_PROVIDER": "openai"}):
            ai = AIService.from_env()
            self.assertIsInstance(ai.provider, OpenAIProvider)
            self.assertEqual(ai.settings.max_output_tokens, 256)
        with patch.dict(os.environ, {"JARVIS_AI_PROVIDER": "disabled"}):
            self.assertIsNone(AIService.from_env().provider)

    def test_request_contract_and_credential_isolation(self):
        history = [{"role": "user", "content": "First question?"},
                   {"role": "assistant", "content": "First answer."},
                   {"role": "user", "content": "Follow up?"}]
        self.assertEqual(self.provider.complete(history), "A concise answer.")
        self.connection_class.assert_called_once_with("generativelanguage.googleapis.com", timeout=15)
        call = self.connection.request.call_args
        self.assertEqual(call.args, ("POST", "/v1beta/openai/chat/completions"))
        body = json.loads(call.kwargs["body"])
        self.assertEqual(body["messages"], [{"role": "system", "content": INSTRUCTIONS}] + history)
        self.assertEqual(body["model"], "gemini-3.8-flash")
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertFalse(body["stream"])
        self.assertEqual(body["tool_choice"], "none")
        for forbidden in ("tools", "functions", "input", "instructions", "store", "previous_response_id"):
            self.assertNotIn(forbidden, body)
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer GeminiSyntheticCredential123")
        for key in ("GeminiSyntheticCredential123", "OpenAISyntheticCredential456"):
            self.assertNotIn(key, call.kwargs["body"].decode())
        self.connection.close.assert_called_once()

    def test_endpoint_override_variables_are_ignored(self):
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://untrusted.invalid",
                                    "JARVIS_AI_ENDPOINT": "http://untrusted.invalid"}):
            self.provider.complete([])
        self.connection_class.assert_called_once_with("generativelanguage.googleapis.com", timeout=15)

    def test_missing_invalid_key_never_falls_back_or_connects(self):
        for key in ("", "   ", "bad\nkey", "bad key", "nonascii-é"):
            with self.subTest(key_kind=len(key)), patch.dict(os.environ, {"GEMINI_API_KEY": key}):
                with self.assertRaisesRegex(AIError, "credentials"):
                    self.provider.complete([])
                self.assertIn("GEMINI_API_KEY", self.service.reply("Hello"))
        self.connection_class.assert_not_called()
        self.assertEqual(self.service._history, [])

    def test_http_failures_are_sanitized_and_connections_closed(self):
        for status, category in ((401, "credentials"), (403, "credentials"), (429, "rate_limit"),
                                 (400, "unavailable"), (500, "unavailable"), (302, "unavailable"),
                                 (307, "unavailable")):
            with self.subTest(status=status):
                self.response.status = status
                with self.assertRaisesRegex(AIError, category):
                    self.provider.complete([])
                self.response.read1.assert_not_called()
        self.assertEqual(self.connection.close.call_count, 7)

    def test_timeout_network_failures_at_each_transport_stage(self):
        for stage in (self.connection.request, self.connection.getresponse, self.response.read1):
            for error, category in ((TimeoutError("GeminiSyntheticCredential123"), "timeout"),
                                    (OSError("GeminiSyntheticCredential123"), "network"),
                                    (http.client.HTTPException("GeminiSyntheticCredential123"), "network")):
                with self.subTest(stage=stage._mock_name, category=category):
                    stage.side_effect = error
                    with self.assertRaisesRegex(AIError, category) as caught:
                        self.provider.complete([])
                    self.assertNotIn("GeminiSyntheticCredential123", str(caught.exception))
                    stage.side_effect = None
        self.assertEqual(self.connection.close.call_count, 9)

    def test_malformed_json_response_shapes_are_rejected(self):
        invalid = [None, [], {}, {"error": {"message": "private details"}},
                   {"choices": None}, {"choices": {}}, {"choices": []}, {"choices": [None]},
                   {"choices": [{"message": None}]}, {"choices": [{"message": []}]},
                   {"choices": [{"message": {"content": "Missing role"}}]},
                   {"choices": [{"message": {"role": "user", "content": "Wrong role"}}]}]
        for result in invalid:
            with self.subTest(shape=type(result).__name__):
                self.response.read1.return_value = json.dumps(result).encode()
                with self.assertRaisesRegex(AIError, "response"):
                    self.provider.complete([])
        for body in (b"not json", b"\xff", b"x" * (MAX_RESPONSE_BYTES + 1)):
            self.response.read1.return_value = body
            with self.assertRaisesRegex(AIError, "response"):
                self.provider.complete([])
        self.response.read1.assert_called_with(MAX_RESPONSE_BYTES + 1)

    def test_non_text_or_empty_content_is_rejected(self):
        for content in (None, "", "  ", 123, {}, [{"text": "Do not coerce"}]):
            with self.subTest(content_type=type(content).__name__):
                self.response.read1.return_value = self.response_body(content)
                with self.assertRaisesRegex(AIError, "response"):
                    self.provider.complete([])

    def test_only_first_choice_is_used(self):
        self.response.read1.return_value = json.dumps({"choices": [
            {"message": {"role": "assistant", "content": "First."}},
            {"message": {"role": "assistant", "content": "Second."}},
        ]}).encode()
        self.assertEqual(self.provider.complete([]), "First.")

    def test_tool_and_legacy_function_calls_are_rejected(self):
        for fields in ({"tool_calls": [{"function": {"name": "shell", "arguments": "private"}}]},
                       {"function_call": {"name": "shell"}}):
            self.response.read1.return_value = self.response_body("Run something.", **fields)
            with self.assertRaisesRegex(AIError, "response"):
                self.provider.complete([])

    def test_configured_timeout_and_model_reach_transport(self):
        with patch.dict(os.environ, {"JARVIS_AI_TIMEOUT": "9", "JARVIS_AI_MODEL": "selected-model"}):
            AIService.from_env().reply("Hello")
        self.connection_class.assert_called_once_with("generativelanguage.googleapis.com", timeout=9)
        self.assertEqual(json.loads(self.connection.request.call_args.kwargs["body"])["model"], "selected-model")

    def test_history_is_bounded_and_failures_do_not_persist(self):
        service = AIService(AISettings(provider="gemini", model="gemini-3.8-flash", history_turns=1), self.provider)
        service.reply("first")
        self.response.status = 429
        self.assertIn("quota", service.reply("failed"))
        self.response.status = 200
        service.reply("second")
        body = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertEqual([message["content"] for message in body["messages"][1:]],
                         ["first", "A concise answer.", "second"])
        self.assertEqual([message["content"] for message in service._history], ["second", "A concise answer."])

    def test_gemini_credentials_are_private_in_history_print_and_tts(self):
        self.response.read1.return_value = self.response_body("GeminiSyntheticCredential123 **Answer.**")
        engine = MagicMock()
        callbacks = {}
        engine.connect.side_effect = lambda event, callback: callbacks.setdefault(event, callback)
        engine.isBusy.return_value = False
        engine.iterate.side_effect = lambda: callbacks["finished-utterance"](None, True)
        with patch.object(jarvis, "engine", engine), patch.object(jarvis, "speech_enabled", True), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.handle_command("Explain GeminiSyntheticCredential123", ai=self.service)
        self.assertNotIn("GeminiSyntheticCredential123", output.getvalue())
        self.assertNotIn("GeminiSyntheticCredential123", str(self.service._history))
        self.assertNotIn("GeminiSyntheticCredential123", engine.say.call_args.args[0])
        self.assertNotIn("GeminiSyntheticCredential123", json.loads(self.connection.request.call_args.kwargs["body"])["messages"][-1]["content"])
        self.assertIn("Answer.", output.getvalue())

    def test_console_tts_and_diagnostics_have_final_redaction(self):
        engine = MagicMock()
        callbacks = {}
        engine.connect.side_effect = lambda event, callback: callbacks.setdefault(event, callback)
        engine.isBusy.return_value = False
        engine.iterate.side_effect = lambda: callbacks["finished-utterance"](None, True)
        with patch.dict(os.environ, {"JARVIS_DEBUG": "1"}), patch.object(jarvis, "engine", engine), \
                patch.object(jarvis, "speech_enabled", True), contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.speak("GeminiSyntheticCredential123")
            jarvis.diagnostic("GeminiSyntheticCredential123")
            jarvis.report_error("GeminiSyntheticCredential123", RuntimeError("private body"))
        self.assertNotIn("GeminiSyntheticCredential123", output.getvalue())
        self.assertNotIn("private body", output.getvalue())
        engine.say.assert_called_once_with("[credential omitted]")

    def test_formatting_cannot_reassemble_visible_credential(self):
        self.assertNotIn("GeminiSyntheticCredential123", voice_text("Gemini`SyntheticCredential123", 600))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "GeminiSynthetic", "GEMINI_API_KEY": "GeminiSyntheticCredential123"}):
            self.assertEqual(redact_credentials("GeminiSyntheticCredential123"), "[credential omitted]")

    def test_error_response_and_unexpected_exception_never_expose_credentials(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.response.status = 401
            answer = self.service.reply("Private question")
            self.assertIn("GEMINI_API_KEY", answer)
            self.assertNotIn("OPENAI_API_KEY", answer)
            self.response.status = 200
            self.connection.request.side_effect = RuntimeError("GeminiSyntheticCredential123 Private question")
            answer = self.service.reply("Private question")
        self.assertNotIn("GeminiSyntheticCredential123", answer + output.getvalue())
        self.assertNotIn("Private question", answer + output.getvalue())
        self.assertEqual(self.service._history, [])

    def test_gemini_text_cannot_trigger_external_actions(self):
        self.response.read1.return_value = self.response_body("open google; email to Raj; run powershell")
        with patch.object(jarvis, "speak"), patch.object(jarvis.webbrowser, "open") as browser, \
                patch.object(jarvis.os, "startfile", create=True) as launch, patch.object(jarvis, "sendEmail") as email:
            jarvis.handle_command("Explain something", ai=self.service)
            for boundary in (browser, launch, email):
                boundary.assert_not_called()

    def test_text_and_voice_integration_builtin_priority_and_cleanup(self):
        for text_mode in (True, False):
            with self.subTest(text_mode=text_mode), patch.object(jarvis, "speak"), \
                    patch.object(jarvis.AIService, "from_env", return_value=self.service), \
                    patch("builtins.input", side_effect=["Explain gravity", "Simplify that", "time", "open youtube", "quit"]) as typed, \
                    patch.object(jarvis, "takeCommand", side_effect=["Explain gravity", "Simplify that", "time", "quit"]) as voice, \
                    patch.object(jarvis.webbrowser, "open") as browser:
                self.connection.request.reset_mock()
                self.assertEqual(jarvis.main(text_mode=text_mode, no_tts=True), 0)
                self.assertEqual(self.connection.request.call_count, 2)
                (voice if text_mode else typed).assert_not_called()
                browser.assert_not_called()
                self.assertEqual(self.service._history, [])


if __name__ == "__main__":
    unittest.main()
