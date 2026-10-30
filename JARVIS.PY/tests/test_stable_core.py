"""Deterministic regression checks; no hardware, browser, or network access."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

spec = importlib.util.spec_from_file_location(
    "jarvis", Path(__file__).resolve().parents[1] / "JARVIS2.0.py"
)
jarvis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jarvis)


class StableCoreTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.failures = patch.object(jarvis, "input_failures", 0)
        self.failures.start()
        self.addCleanup(self.failures.stop)
        self.calibration = patch.object(jarvis, "calibrated_microphone", None)
        self.calibration.start()
        self.addCleanup(self.calibration.stop)
        self.noise = patch.object(jarvis.Listener, "adjust_for_ambient_noise")
        self.noise.start()
        self.addCleanup(self.noise.stop)
        self.speech = patch.object(jarvis, "speak")
        self.speak = self.speech.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.speech.stop)

    def test_import_does_not_start_speech(self):
        self.assertIsNone(jarvis.engine)

    def test_greeting(self):
        jarvis.wishMe()
        self.assertEqual(self.speak.call_count, 2)
        self.assertIn(self.speak.call_args_list[0].args[0],
                      ("Good Morning!", "Good Afternoon!", "Good Evening!"))

    def test_time_and_browser(self):
        self.assertTrue(jarvis.handle_command("What's the time?"))
        self.assertIn("the time is", self.speak.call_args.args[0])
        with patch.object(jarvis.webbrowser, "open", return_value=True) as browser:
            self.assertTrue(jarvis.handle_command("Open YouTube"))
            browser.assert_called_once_with("https://www.youtube.com")

    def test_time_variations_reach_action(self):
        for phrase in ("what's the time", "what is the time", "tell me the time",
                       "time", "  WHAT’S   THE TIME?  ", "time please"):
            with self.subTest(phrase=phrase), contextlib.redirect_stdout(io.StringIO()) as output:
                self.speak.reset_mock()
                self.assertTrue(jarvis.handle_command(phrase))
                self.speak.assert_called_once()
                response = self.speak.call_args.args[0]
                self.assertRegex(response, r"the time is \d{2}:\d{2}:\d{2}")
                self.assertIn(response, output.getvalue())

    def test_recognition_to_routing(self):
        # Only the external boundaries are mocked: recognition return values
        # pass through the real takeCommand, main loop, normalization and routing.
        phrases = ("what's the time", "what is the time", "open youtube",
                   "open google", "wikipedia albert einstein", "unknown command", "quit")
        with patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", side_effect=phrases), \
                patch.object(jarvis.webbrowser, "open", return_value=True) as browser, \
                patch.object(jarvis.wikipedia, "summary", return_value="Einstein summary") as summary:
            jarvis.main()
            self.assertEqual(browser.call_args_list[0].args, ("https://www.youtube.com",))
            self.assertEqual(browser.call_args_list[1].args, ("https://www.google.com",))
            summary.assert_called_once_with("albert einstein", sentences=2)
            spoken = [call.args[0] for call in self.speak.call_args_list]
            self.assertEqual(sum("the time is" in text for text in spoken), 2)
            self.assertIn("Einstein summary", spoken)
            self.assertIn("Please say the command again, sir.", spoken)
            self.assertEqual(spoken[-1], "Goodbye, sir.")

    def test_all_browser_variations(self):
        for phrase, url in (("open youtube", "https://www.youtube.com"),
                            ("Open You Tube!", "https://www.youtube.com"),
                            ("please open google", "https://www.google.com"),
                            ("open stack overflow", "https://stackoverflow.com"),
                            ("open stackoverflow", "https://stackoverflow.com")):
            with self.subTest(phrase=phrase), \
                    patch.object(jarvis.webbrowser, "open", return_value=True) as browser:
                self.assertTrue(jarvis.handle_command(phrase))
                browser.assert_called_once_with(url)

    def test_unknown_command_and_word_boundaries(self):
        for phrase in ("unknown command", "sometimes", "open googleplex", "wikipediathing"):
            with self.subTest(phrase=phrase), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    patch.object(jarvis.webbrowser, "open") as browser:
                self.assertTrue(jarvis.handle_command(phrase))
                self.assertIn("No matching command", output.getvalue())
                self.assertNotIn(phrase, output.getvalue())
                browser.assert_not_called()
        with patch.dict(os.environ, {"JARVIS_DEBUG": "1"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.handle_command("unknown command")
            self.assertIn("route=unknown", output.getvalue())
            self.assertNotIn("unknown command", output.getvalue())

    def test_music_code_jokes_and_conversation(self):
        with patch.dict(os.environ, {"JARVIS_MUSIC_DIR": "music", "JARVIS_CODE_PATH": "Code.exe"}), \
                patch.object(jarvis.os, "listdir", return_value=["b.mp3", "a.txt", "a.wav"]), \
                patch.object(jarvis.os.path, "isfile", return_value=True), \
                patch.object(jarvis.os, "startfile") as launch:
            jarvis.handle_command("play music")
            launch.assert_called_with(os.path.join("music", "a.wav"))
            jarvis.handle_command("open visual studio code")
            launch.assert_called_with("Code.exe")
        with patch.object(jarvis.pyjokes, "get_joke", return_value="A joke") as joke:
            jarvis.handle_command("tell me jokes")
            joke.assert_called_once_with()
            self.speak.assert_called_with("A joke")
        jarvis.handle_command("are you single?")
        self.speak.assert_called_with("I am in a relationship with wifi")

    def test_exit_with_recognition_punctuation(self):
        for phrase in ("Quit!", "EXIT."):
            self.assertFalse(jarvis.handle_command(phrase))

    def test_calibration_once_and_explicit_device_settings(self):
        with patch.object(jarvis.sr, "Microphone") as mic, \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="time"):
            jarvis.takeCommand()
            jarvis.takeCommand()
            self.assertEqual(jarvis.Listener.adjust_for_ambient_noise.call_count, 1)
            with patch.dict(os.environ, {"JARVIS_MIC_DEVICE_INDEX": "1",
                                        "JARVIS_MIC_SAMPLE_RATE": "44100"}):
                jarvis.takeCommand()
                mic.assert_called_with(device_index=1, sample_rate=44100, chunk_size=1024)
                self.assertEqual(jarvis.Listener.adjust_for_ambient_noise.call_count, 2)

    def test_transcript_privacy_and_sensitive_dictation(self):
        for debug, sensitive in ((False, False), (True, True)):
            with patch.dict(os.environ, {"JARVIS_DEBUG": str(int(debug))}), \
                    patch.object(jarvis.sr, "Microphone"), \
                    patch.object(jarvis.Listener, "listen"), \
                    patch.object(jarvis.Listener, "recognize_google", return_value="PRIVATE_TEST_BODY"), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(jarvis.takeCommand(sensitive=sensitive), "PRIVATE_TEST_BODY")
                self.assertNotIn("PRIVATE_TEST_BODY", output.getvalue())

    def test_wikipedia_timeout_https_and_state_restoration(self):
        api = jarvis.wikipedia.wikipedia
        original_requests, original_url = api.requests, api.API_URL

        def fake_summary(*args, **kwargs):
            self.assertTrue(api.API_URL.startswith("https://"))
            return api.requests.get(api.API_URL)

        with patch.object(original_requests, "get", side_effect=TimeoutError()) as get, \
                patch.object(jarvis.wikipedia, "summary", side_effect=fake_summary):
            self.assertTrue(jarvis.handle_command("wikipedia topic"))
            self.assertEqual(get.call_args.kwargs["timeout"], (3, 5))
        self.assertIs(api.requests, original_requests)
        self.assertEqual(api.API_URL, original_url)

    def test_wikipedia_preserves_topic_punctuation(self):
        with patch.object(jarvis.wikipedia, "summary", return_value="A language") as summary:
            jarvis.handle_command("Wikipedia C++")
            summary.assert_called_once_with("c++", sentences=2)

    def test_tts_external_loop_repeated_success(self):
        self.speech.stop()
        callbacks = {}
        fake_engine = MagicMock()
        fake_engine.getProperty.return_value = []

        def connect(event, callback):
            callbacks[event] = callback
            return event

        fake_engine.connect.side_effect = connect
        fake_engine.isBusy.return_value = False
        fake_engine.iterate.side_effect = lambda: callbacks["finished-utterance"](None, True)
        with patch.object(jarvis, "engine", None), \
                patch.object(jarvis.pyttsx3, "init", return_value=fake_engine) as initialize:
            for text in ("First", "Second", "Third"):
                jarvis.speak(text)
            initialize.assert_called_once_with("sapi5")
            self.assertEqual(fake_engine.say.call_count, 3)
            self.assertEqual(fake_engine.endLoop.call_count, 3)
            fake_engine.runAndWait.assert_not_called()

    def test_tts_cancellation_error_and_deadline(self):
        self.speech.stop()
        for mode in ("cancelled", "error", "timeout"):
            with self.subTest(mode=mode):
                callbacks = {}
                fake_engine = MagicMock()
                fake_engine.connect.side_effect = lambda event, cb: callbacks.setdefault(event, cb)
                fake_engine.isBusy.return_value = mode == "timeout"

                def iterate():
                    if mode == "cancelled":
                        callbacks["finished-utterance"](None, False)
                    elif mode == "error":
                        callbacks["error"](None, RuntimeError("PRIVATE_TEST_BODY"))

                fake_engine.iterate.side_effect = iterate
                with patch.object(jarvis, "engine", fake_engine), \
                        patch.object(jarvis.time, "monotonic", side_effect=[0, 1000]), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    jarvis.speak("Public response")
                    self.assertIsNone(jarvis.engine)
                    self.assertIn("Speech unavailable", output.getvalue())
                    self.assertNotIn("PRIVATE_TEST_BODY", output.getvalue())
                    fake_engine.endLoop.assert_called_once()

    def test_email_body_is_not_normalized_or_logged(self):
        with patch.dict(os.environ, {"JARVIS_EMAIL_ADDRESS": "sender@example.com",
                                    "JARVIS_EMAIL_PASSWORD": "TEST_PLACEHOLDER",
                                    "JARVIS_EMAIL_TO": "recipient@example.com"}), \
                patch.object(jarvis, "takeCommand", return_value="PRIVATE_TEST_BODY: C++!") as take, \
                patch.object(jarvis, "sendEmail") as send, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(jarvis.handle_command("Email to Raj", confirm_fn=lambda: "confirm send"))
            take.assert_called_once_with(sensitive=True)
            send.assert_called_once_with("recipient@example.com", "PRIVATE_TEST_BODY: C++!")
            self.assertNotIn("PRIVATE_TEST_BODY", output.getvalue())

    def test_recognized_input_and_limits(self):
        with patch.object(jarvis.sr, "Microphone") as mic, \
                patch.object(jarvis.Listener, "listen") as listen, \
                patch.object(jarvis.Listener, "recognize_google", return_value=" Exit "):
            self.assertEqual(jarvis.takeCommand(), "Exit")
            mic.assert_called_once_with(device_index=None, sample_rate=None, chunk_size=1024)
            listen.assert_called_once_with(mic.return_value.__enter__.return_value,
                                          timeout=5, phrase_time_limit=10)
        with patch.dict(os.environ, {"JARVIS_MIC_DEVICE_INDEX": "default"}), \
                patch.object(jarvis.sr, "Microphone") as mic, \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="time"):
            jarvis.takeCommand()
            self.assertIsNone(mic.call_args.kwargs["device_index"])

    def test_input_failures_return_none_and_delay(self):
        for error in (jarvis.sr.WaitTimeoutError(), jarvis.sr.UnknownValueError(),
                      jarvis.sr.RequestError("offline"), OSError("device unavailable")):
            with self.subTest(error=type(error).__name__), \
                    patch.object(jarvis.sr, "Microphone"), \
                    patch.object(jarvis.Listener, "listen", side_effect=error), \
                    patch.object(jarvis.time, "sleep") as sleep:
                self.assertIsNone(jarvis.takeCommand())
                self.assertGreaterEqual(sleep.call_args.args[0], 1)

    def test_microphone_open_and_invalid_config(self):
        with patch.object(jarvis.sr, "Microphone", side_effect=OSError()), \
                patch.object(jarvis.time, "sleep"):
            self.assertIsNone(jarvis.takeCommand())
        with patch.dict(os.environ, {"JARVIS_MIC_DEVICE_INDEX": "invalid"}), \
                patch.object(jarvis.time, "sleep"):
            self.assertIsNone(jarvis.takeCommand())

    def test_recognition_service_failure(self):
        with patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google",
                             side_effect=jarvis.sr.RequestError("offline")), \
                patch.object(jarvis.time, "sleep"):
            self.assertIsNone(jarvis.takeCommand())

    def test_empty_recognition_delays_retry(self):
        with patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="  "), \
                patch.object(jarvis.time, "sleep") as sleep:
            self.assertIsNone(jarvis.takeCommand())
            self.assertEqual(sleep.call_args.args[0], 1)

    def test_configured_recognition_and_thresholds(self):
        with patch.dict(os.environ, {"JARVIS_RECOGNITION_LANGUAGE": "en-GB",
                                    "JARVIS_LISTEN_TIMEOUT": "9", "JARVIS_PHRASE_TIME_LIMIT": "15",
                                    "JARVIS_RECOGNITION_TIMEOUT": "12", "JARVIS_PAUSE_THRESHOLD": "1.2",
                                    "JARVIS_DYNAMIC_ENERGY": "false", "JARVIS_ENERGY_THRESHOLD": "450",
                                    "JARVIS_CALIBRATION_DURATION": "0", "JARVIS_MIC_CHUNK_SIZE": "2048"}), \
                patch.object(jarvis.sr, "Microphone") as mic, \
                patch.object(jarvis.Listener, "listen") as listen, \
                patch.object(jarvis.Listener, "recognize_google", return_value="time") as recognize:
            self.assertEqual(jarvis.takeCommand(), "time")
            recognize.assert_called_once_with(listen.return_value, language="en-GB",
                                              endpoint=jarvis.GOOGLE_RECOGNITION_ENDPOINT)
            listen.assert_called_once_with(mic.return_value.__enter__.return_value,
                                          timeout=9, phrase_time_limit=15)
            self.assertEqual(jarvis.Listener.energy_threshold, 450)
            self.assertFalse(jarvis.Listener.dynamic_energy_threshold)
            self.assertEqual(jarvis.Listener.operation_timeout, 12)
            jarvis.Listener.adjust_for_ambient_noise.assert_not_called()

    def test_settings_validation_and_startup_failure(self):
        for name, value in (("JARVIS_LISTEN_TIMEOUT", "0"), ("JARVIS_PAUSE_THRESHOLD", "nan"),
                            ("JARVIS_MIC_DEVICE_INDEX", "-1"), ("JARVIS_MIC_SAMPLE_RATE", "bad"),
                            ("JARVIS_DYNAMIC_ENERGY", "PRIVATE_TEST_BODY")):
            with self.subTest(name=name), patch.dict(os.environ, {name: value}), \
                    patch.object(jarvis.sr, "Microphone") as mic, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(jarvis.main(), 2)
                mic.assert_not_called()
                self.assertIn(name, output.getvalue())
                if value == "PRIVATE_TEST_BODY":
                    self.assertNotIn(value, output.getvalue())

    def test_repeated_failure_backoff_and_success_reset(self):
        with patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen", side_effect=jarvis.sr.UnknownValueError()), \
                patch.object(jarvis.time, "sleep") as sleep:
            delays = []
            for _ in range(6):
                self.assertIsNone(jarvis.takeCommand())
                delays.append(sleep.call_args.args[0])
            self.assertEqual(delays, [1, 2, 4, 8, 8, 8])
        with patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="time"):
            jarvis.takeCommand()
            self.assertEqual(jarvis.input_failures, 0)

    def test_debug_never_logs_transcripts(self):
        with patch.dict(os.environ, {"JARVIS_DEBUG": "1"}), \
                patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="PRIVATE_TEST_BODY"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.handle_command(jarvis.takeCommand())
            self.assertIn("recognition succeeded", output.getvalue())
            self.assertNotIn("PRIVATE_TEST_BODY", output.getvalue())

    def test_equivalent_command_phrases(self):
        for phrase, route in (("what time is it?", "time"), ("current time", "time"),
                              ("Jarvis, what's the current time?", "time"),
                              ("launch YouTube", "youtube"), ("open up Google", "google"),
                              ("start VS Code", "code"), ("start music", "music"),
                              ("please quit", "exit"), ("Jarvis exit please", "exit")):
            with self.subTest(phrase=phrase):
                self.assertEqual(jarvis.command_for(phrase), route)
        self.assertEqual(jarvis.command_for("please exit wikipedia"), "wikipedia")

    def test_text_mode_dry_run_has_no_external_effects(self):
        self.speech.stop()
        with patch("builtins.input", side_effect=["time", "open youtube", "email to Raj", "exit"]), \
                patch.object(jarvis.sr, "Microphone") as mic, \
                patch.object(jarvis.webbrowser, "open") as browser, \
                patch.object(jarvis, "sendEmail") as email, \
                patch.object(jarvis.pyttsx3, "init") as tts, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(jarvis.main(text_mode=True, no_tts=True), 0)
            for boundary in (mic, browser, email, tts):
                boundary.assert_not_called()
            self.assertIn("the time is", output.getvalue())
            self.assertIn("Dry run: youtube", output.getvalue())

    def test_text_execute_and_eof_exit(self):
        with patch("builtins.input", side_effect=["open google", EOFError]), \
                patch.object(jarvis.webbrowser, "open", return_value=True) as browser, \
                patch.object(jarvis.sr, "Microphone") as mic:
            self.assertEqual(jarvis.main(text_mode=True, execute=True), 0)
            browser.assert_called_once_with("https://www.google.com")
            mic.assert_not_called()

    def test_tts_probe_avoids_microphone(self):
        with patch.object(jarvis.sr, "Microphone") as mic:
            self.assertEqual(jarvis.main(tts_test=True), 0)
            self.assertEqual(self.speak.call_count, 3)
            mic.assert_not_called()

    def test_microphone_inventory_filters_outputs_and_cleans_up(self):
        audio = MagicMock()
        audio.get_device_count.return_value = 2
        audio.get_device_info_by_index.side_effect = [
            {"name": "Input test", "maxInputChannels": 1, "defaultSampleRate": 48000},
            {"name": "Output test", "maxInputChannels": 0, "defaultSampleRate": 48000}]
        with patch.object(jarvis.sr.Microphone, "get_pyaudio") as module, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            module.return_value.PyAudio.return_value = audio
            self.assertEqual(jarvis.list_microphones(), 0)
            self.assertIn("Input test", output.getvalue())
            self.assertNotIn("Output test", output.getvalue())
            audio.terminate.assert_called_once()

    def test_short_pause_is_compatible_with_recognizer(self):
        with patch.dict(os.environ, {"JARVIS_PAUSE_THRESHOLD": "0.3"}), \
                patch.object(jarvis.sr, "Microphone"), \
                patch.object(jarvis.Listener, "listen"), \
                patch.object(jarvis.Listener, "recognize_google", return_value="time"):
            jarvis.takeCommand()
            self.assertLessEqual(jarvis.Listener.non_speaking_duration, jarvis.Listener.pause_threshold)

    def test_cli_rejects_unsafe_or_conflicting_options(self):
        for options in (["--execute"], ["--tts-test", "--no-tts"]):
            with patch.object(jarvis.argparse._sys, "argv", ["JARVIS2.0.py", *options]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_error:
                    jarvis.cli()
                self.assertEqual(exit_error.exception.code, 2)

    def test_wikipedia_empty_success_and_failures(self):
        with patch.object(jarvis.wikipedia, "summary", return_value="A summary") as summary:
            jarvis.handle_command("wikipedia")
            summary.assert_not_called()
            self.assertTrue(jarvis.handle_command("wikipedia Python"))
            summary.assert_called_once_with("python", sentences=2)
        for error in (jarvis.wikipedia.exceptions.DisambiguationError("a", ["b"]),
                      jarvis.wikipedia.exceptions.PageError("missing"),
                      ConnectionError("offline"), RuntimeError("library failure")):
            with self.subTest(error=type(error).__name__), \
                    patch.object(jarvis.wikipedia, "summary", side_effect=error):
                self.assertTrue(jarvis.handle_command("wikipedia topic"))

    def test_exit_quit_and_main_loop(self):
        for command in ("Exit", " quit "):
            self.assertFalse(jarvis.handle_command(command))
        with patch.object(jarvis, "takeCommand", side_effect=[None, "the time", "quit"]) as take:
            jarvis.main()
            self.assertEqual(take.call_count, 3)
        with patch.object(jarvis, "takeCommand", side_effect=KeyboardInterrupt):
            jarvis.main()

    def test_missing_optional_configuration(self):
        for command in ("play music", "open code", "email to Raj"):
            self.assertTrue(jarvis.handle_command(command))
        with patch.object(jarvis.smtplib, "SMTP") as smtp:
            with self.assertRaises(ValueError):
                jarvis.sendEmail("recipient@example.com", "hello")
            smtp.assert_not_called()

    def test_external_and_path_errors_are_recoverable(self):
        with patch.object(jarvis.webbrowser, "open", side_effect=OSError()):
            self.assertTrue(jarvis.handle_command("open google"))
        with patch.object(jarvis.webbrowser, "open", return_value=False):
            self.assertTrue(jarvis.handle_command("open google"))
        with patch.dict(os.environ, {"JARVIS_MUSIC_DIR": "missing"}), \
                patch.object(jarvis.os, "listdir", side_effect=FileNotFoundError()):
            self.assertTrue(jarvis.handle_command("play music"))
        with patch.dict(os.environ, {"JARVIS_CODE_PATH": "missing"}), \
                patch.object(jarvis.os, "startfile", side_effect=FileNotFoundError()):
            self.assertTrue(jarvis.handle_command("open code"))

    def test_email_cancel_exit_and_failure(self):
        with patch.dict(os.environ, {"JARVIS_EMAIL_ADDRESS": "sender@example.com",
                                    "JARVIS_EMAIL_PASSWORD": "TEST_PLACEHOLDER",
                                    "JARVIS_EMAIL_TO": "recipient@example.com"}):
            for content in (None, "exit", "hello"):
                with patch.object(jarvis, "takeCommand", return_value=content), \
                        patch.object(jarvis, "sendEmail", side_effect=OSError()) as send:
                    self.assertEqual(jarvis.handle_command("email to Raj", confirm_fn=lambda: "confirm send"), content != "exit")
                    self.assertEqual(send.call_count, int(content == "hello"))

    def test_smtp_cleanup_and_secret_redaction(self):
        with patch.dict(os.environ, {"JARVIS_EMAIL_ADDRESS": "sender@example.com",
                                    "JARVIS_EMAIL_PASSWORD": "TEST_PLACEHOLDER"}), \
                patch.object(jarvis.smtplib, "SMTP") as smtp:
            smtp.return_value.__enter__.return_value.ehlo.return_value = (250, b"ok")
            jarvis.sendEmail("recipient@example.com", "hello")
            smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
            smtp.return_value.__exit__.assert_called_once()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            jarvis.report_error("Email failed", RuntimeError("TEST_PLACEHOLDER"))
        self.assertNotIn("TEST_PLACEHOLDER", output.getvalue())

    def test_tts_failure_falls_back_and_cleanup(self):
        self.speech.stop()
        with patch.object(jarvis, "engine", None), \
                patch.object(jarvis.pyttsx3, "init", side_effect=RuntimeError()), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            jarvis.speak("Fallback response")
            self.assertIn("Fallback response", output.getvalue())
        fake_engine = MagicMock()
        with patch.object(jarvis, "engine", fake_engine), \
                patch.object(jarvis, "speak"), \
                patch.object(jarvis, "takeCommand", return_value="exit"):
            jarvis.main()
            fake_engine.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
