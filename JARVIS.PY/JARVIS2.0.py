"""JARVIS v0.3 — AI Brain, Phase 1.1 Gemini Integration (Windows)."""

import argparse
import datetime
import getpass
import math
import os
import re
import smtplib
import ssl
import time
import webbrowser
from email.message import EmailMessage
from email.policy import SMTP
from functools import partial
from types import SimpleNamespace

import pyjokes
import pyttsx3
import speech_recognition as sr
import wikipedia

from ai_service import AIService, redact_credentials

Listener = sr.Recognizer()
Listener.pause_threshold = 1
Listener.dynamic_energy_threshold = True
Listener.operation_timeout = 10
engine = None
calibrated_microphone = None
input_failures = 0
speech_enabled = True


def number_setting(name, default, minimum, maximum, integer=False):
    value = os.getenv(name, "").strip()
    try:
        parsed = (int if integer else float)(value) if value else default
        if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
            raise ValueError
        return parsed
    except ValueError:
        # Never echo configuration values, which might contain private data.
        raise ValueError(f"Invalid {name}; expected {minimum} to {maximum}") from None


def bool_setting(name, default):
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    raise ValueError(f"Invalid {name}; expected true or false")


def voice_settings():
    device = os.getenv("JARVIS_MIC_DEVICE_INDEX", "default").strip().lower()
    return {
        "device": None if device in ("", "default") else number_setting(
            "JARVIS_MIC_DEVICE_INDEX", 0, 0, 10000, integer=True),
        "sample_rate": number_setting("JARVIS_MIC_SAMPLE_RATE", 16000, 8000, 192000, True)
        if os.getenv("JARVIS_MIC_SAMPLE_RATE", "").strip() else None,
        "chunk": number_setting("JARVIS_MIC_CHUNK_SIZE", 1024, 128, 8192, True),
        "language": os.getenv("JARVIS_RECOGNITION_LANGUAGE", "en-in").strip() or "en-in",
        "timeout": number_setting("JARVIS_LISTEN_TIMEOUT", 5, 1, 60),
        "phrase_limit": number_setting("JARVIS_PHRASE_TIME_LIMIT", 10, 1, 60),
        "service_timeout": number_setting("JARVIS_RECOGNITION_TIMEOUT", 10, 1, 60),
        "calibration": number_setting("JARVIS_CALIBRATION_DURATION", 1, 0, 5),
        "energy": number_setting("JARVIS_ENERGY_THRESHOLD", 300, 1, 10000),
        "dynamic": bool_setting("JARVIS_DYNAMIC_ENERGY", True),
        "pause": number_setting("JARVIS_PAUSE_THRESHOLD", 1, 0.3, 3),
        "phrase_threshold": number_setting("JARVIS_PHRASE_THRESHOLD", 0.2, 0.05, 3),
        "settle": number_setting("JARVIS_AUDIO_SETTLE_TIME", 0.3, 0, 3),
        "retry": number_setting("JARVIS_RETRY_DELAY", 1, 0.5, 10),
        "max_retry": number_setting("JARVIS_MAX_RETRY_DELAY", 8, 1, 30),
    }


def diagnostic(message):
    if debug_enabled():
        print(redact_credentials(f"DEBUG: {message}"))


def debug_enabled():
    return os.getenv("JARVIS_DEBUG", "").strip().lower() in ("1", "true", "yes")


def normalize_query(query):
    query = query.casefold().replace("’", "'").replace("'", "")
    return " ".join(re.sub(r"[^\w\s]", " ", query).split())


def has_phrase(query, *phrases):
    return any(f" {phrase} " in f" {query} " for phrase in phrases)


def command_for(query):
    """Match only the existing allowlisted commands; never execute input as code."""
    query = normalize_query(query)
    # Polite wrappers are safe only around exact shutdown commands.
    shutdown = re.sub(r"^(?:jarvis |please )+|(?: please)+$", "", query)
    if shutdown in ("exit", "quit"):
        return "exit"
    if shutdown in ("help", "commands", "what can you do"):
        return "help"
    if shutdown in ("clear conversation", "reset conversation"):
        return "reset_conversation"
    if has_phrase(query, "wikipedia"):
        return "wikipedia"
    for command, targets in (("youtube", ("youtube", "you tube")),
                             ("google", ("google",)),
                             ("stackoverflow", ("stackoverflow", "stack overflow")),
                             ("code", ("code", "vs code", "visual studio code"))):
        if re.search(r"\b(?:open|launch|start)(?: up)? (?:" + "|".join(targets) + r")\b", query):
            return command
    if has_phrase(query, "play music", "start music"):
        return "music"
    if has_phrase(query, "the time") or re.fullmatch(
        r"(?:jarvis )?(?:please )?(?:(?:whats|what is|tell me)(?: the| current)? )?"
        r"(?:current )?time(?: (?:now|please))?|(?:please )?what time is it(?: please)?", query
    ):
        return "time"
    if has_phrase(query, "email to raj", "send email to raj", "email raj"):
        return "email"
    if has_phrase(query, "are you single"):
        return "conversation"
    if has_phrase(query, "joke", "jokes"):
        return "joke"
    return None


def report_error(context, error):
    # Exception messages can contain credentials or email content.
    print(redact_credentials(f"{context}: {type(error).__name__}"))


def speak(audio):
    global engine
    audio = redact_credentials(audio)
    print(f"Jarvis: {audio}")
    if not speech_enabled:
        return
    loop_started = False
    connections = []
    completion = []
    errors = []
    try:
        if engine is None:
            engine = pyttsx3.init("sapi5")
            voices = engine.getProperty("voices")
            if voices:
                index = number_setting("JARVIS_TTS_VOICE_INDEX", 0, 0, len(voices) - 1, True)
                engine.setProperty("voice", voices[index].id)
            engine.setProperty("rate", number_setting("JARVIS_TTS_RATE", 200, 80, 350, True))
            engine.setProperty("volume", number_setting("JARVIS_TTS_VOLUME", 1, 0, 1))
        connections.append(engine.connect(
            "finished-utterance", lambda name, completed: completion.append(completed)
        ))
        connections.append(engine.connect(
            "error", lambda name, exception: errors.append(exception)
        ))
        engine.say(audio)
        # pyttsx3 2.99's SAPI5 driver can cancel repeated runAndWait() calls.
        # The public external loop avoids its queued endLoop command.
        engine.startLoop(False)
        loop_started = True
        deadline = time.monotonic() + min(120, max(15, len(audio) / 8))
        engine.iterate()
        while engine.isBusy() and time.monotonic() < deadline:
            engine.iterate()
            time.sleep(0.01)
        if errors:
            raise errors[0]
        if not completion or not completion[-1]:
            raise RuntimeError("Speech did not complete")
        if debug_enabled():
            print("DEBUG: TTS utterance completed (audibility requires manual verification).")
    except Exception as error:
        report_error("Text-to-speech failed", error)
        print("Speech unavailable; response printed above.")
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
    finally:
        if engine is not None:
            if loop_started:
                try:
                    engine.endLoop()
                except Exception as error:
                    report_error("Speech loop cleanup failed", error)
            for connection in connections:
                try:
                    engine.disconnect(connection)
                except Exception as error:
                    report_error("Speech callback cleanup failed", error)
            if not completion or not completion[-1] or errors:
                engine = None


def wishMe():
    hour = datetime.datetime.now().hour
    if hour < 12:
        speak("Good Morning!")
    elif hour < 18:
        speak("Good Afternoon!")
    else:
        speak("Good Evening!")
    speak("Jarvis here at your service, sir. How may I help you?")


def takeCommand(sensitive=False):
    """Return recognized speech, or None after a recoverable input failure."""
    global calibrated_microphone, input_failures
    settings = None
    try:
        settings = voice_settings()
        Listener.operation_timeout = settings["service_timeout"]
        Listener.pause_threshold = settings["pause"]
        Listener.non_speaking_duration = min(0.5, settings["pause"])
        Listener.phrase_threshold = settings["phrase_threshold"]
        Listener.dynamic_energy_threshold = settings["dynamic"]
        time.sleep(settings["settle"])
        with sr.Microphone(
            device_index=settings["device"], sample_rate=settings["sample_rate"],
            chunk_size=settings["chunk"]
        ) as source:
            calibration_key = tuple(settings[key] for key in
                                    ("device", "sample_rate", "chunk", "energy", "calibration", "dynamic"))
            if calibrated_microphone != calibration_key:
                Listener.energy_threshold = settings["energy"]
                if settings["calibration"]:
                    print("Calibrating microphone; please stay quiet...")
                    Listener.adjust_for_ambient_noise(source, duration=settings["calibration"])
                calibrated_microphone = calibration_key
            diagnostic(f"capture ready; energy_threshold={Listener.energy_threshold:.0f}; "
                       f"dynamic_energy={Listener.dynamic_energy_threshold}")
            print("Listening...")
            audio = Listener.listen(source, timeout=settings["timeout"],
                                    phrase_time_limit=settings["phrase_limit"])
        print("Recognizing...")
        query = Listener.recognize_google(audio, language=settings["language"]).strip()
        # Dictated email may contain sensitive content: do not log transcripts.
        print("Command recognized." if query else "No speech recognized.")
        if query:
            input_failures = 0
            diagnostic("recognition succeeded; transcript omitted")
            return query
    except sr.WaitTimeoutError:
        print("No speech detected. Listening again shortly.")
    except sr.UnknownValueError:
        print("Could not understand speech. Please repeat your command.")
    except sr.RequestError as error:
        report_error("Speech recognition service unavailable", error)
        if input_failures == 0:
            speak("Speech recognition is unavailable. Please check your connection.")
    except Exception as error:
        report_error("Microphone or speech input failed", error)
        print("Check your microphone, permissions, and JARVIS_MIC_DEVICE_INDEX.")
        calibrated_microphone = None
    input_failures += 1
    retry = settings["retry"] if settings else 1
    maximum = settings["max_retry"] if settings else 8
    delay = min(maximum, retry * 2 ** min(input_failures - 1, 5))
    diagnostic(f"input failure count={input_failures}; retry delay={delay:g}s")
    if input_failures == 3:
        print("Repeated input failures. Check the input device, noise level and language; "
              "Ctrl+C stops Jarvis. Try --text --no-tts to isolate routing.")
    time.sleep(delay)
    return None


def sendEmail(to, content):
    address = os.getenv("JARVIS_EMAIL_ADDRESS", "").strip()
    password = os.getenv("JARVIS_EMAIL_PASSWORD", "")
    if not address or not password or not to:
        raise ValueError("Email configuration is missing")
    # Accept one bare ASCII mailbox per envelope field, never SMTP control text.
    for mailbox in (address, to):
        if not isinstance(mailbox, str) or not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?",
            mailbox,
        ):
            raise ValueError("Email address configuration is invalid")
    if not content:
        raise ValueError("Email content is empty")
    message = EmailMessage()
    message["From"] = address
    message["To"] = to
    message.set_content(content, charset="utf-8", cte="quoted-printable")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        server.login(address, password)
        server.sendmail(address, to, message.as_bytes(policy=SMTP))


def search_wikipedia(query):
    topic = re.sub(r"\bwikipedia\b", "", query, flags=re.IGNORECASE).strip()
    if not topic:
        speak("Please say Wikipedia followed by a topic.")
        return
    speak("Searching Wikipedia...")
    try:
        # wikipedia 1.4.0 has no public timeout option. Limit only its HTTP
        # calls in this synchronous lookup; always restore the library state.
        api = wikipedia.wikipedia
        original_requests, original_url = api.requests, api.API_URL
        try:
            api.requests = SimpleNamespace(get=partial(original_requests.get, timeout=(3, 5)))
            api.API_URL = original_url.replace("http://", "https://", 1)
            results = wikipedia.summary(topic, sentences=2)
        finally:
            api.requests, api.API_URL = original_requests, original_url
    except wikipedia.exceptions.DisambiguationError as error:
        report_error("Wikipedia topic is ambiguous", error)
        speak("That topic has several meanings. Please use a more specific name.")
    except wikipedia.exceptions.PageError as error:
        report_error("Wikipedia page not found", error)
        speak("I could not find that Wikipedia page. Please try another topic.")
    except Exception as error:
        report_error("Wikipedia lookup failed", error)
        speak("Wikipedia is unavailable right now. Please try again later.")
    else:
        speak("According to Wikipedia")
        print(results)
        speak(results)


def open_website(url):
    print(f"Opening website: {url}")
    if not webbrowser.open(url):
        speak("I could not open your browser. Please check your default browser.")


def handle_command(query, dry_run=False, input_fn=None, ai=None, confirm_fn=None):
    """Execute a command; return False when the user requests shutdown."""
    original_query = query.casefold().strip()
    command = command_for(query)
    diagnostic(f"route={command or 'unknown'}; transcript omitted")
    if command == "exit":
        speak("Goodbye, sir.")
        return False
    if dry_run and command in ("wikipedia", "youtube", "google", "stackoverflow", "music", "code", "email"):
        print(f"Dry run: {command}; external action skipped.")
        return True
    try:
        if command == "help":
            speak("Try time, open YouTube, open Google, open Stack Overflow, "
                  "Wikipedia followed by a topic, play music, open code, tell me a joke, "
                  "email to Raj, clear conversation, or quit. "
                  "Email requires configuration and confirmation.")
        elif command == "reset_conversation":
            if ai is not None:
                ai.clear()
            speak("Local conversation history cleared. Provider records are unaffected.")
        elif command == "wikipedia":
            search_wikipedia(original_query)
        elif command == "youtube":
            open_website("https://www.youtube.com")
        elif command == "google":
            open_website("https://www.google.com")
        elif command == "stackoverflow":
            open_website("https://stackoverflow.com")
        elif command == "music":
            music_dir = os.getenv("JARVIS_MUSIC_DIR", "")
            if not music_dir:
                speak("Please configure JARVIS_MUSIC_DIR to play music.")
                return True
            songs = sorted(
                path for path in os.listdir(music_dir)
                if os.path.isfile(os.path.join(music_dir, path))
                and os.path.splitext(path)[1].lower() in
                (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma", ".aac")
            )
            if not songs:
                speak("There are no supported audio files in your music folder.")
            else:
                print("Opening audio file.")
                os.startfile(os.path.join(music_dir, songs[0]))
        elif command == "time":
            strTime = datetime.datetime.now().strftime("%H:%M:%S")
            response = f"Sir, the time is {strTime}"
            print(response)
            speak(response)
        elif command == "code":
            code_path = os.getenv("JARVIS_CODE_PATH", "")
            if not code_path:
                speak("Please configure JARVIS_CODE_PATH to open Visual Studio Code.")
            else:
                print("Opening Visual Studio Code.")
                os.startfile(code_path)
        elif command == "email":
            address = os.getenv("JARVIS_EMAIL_ADDRESS", "").strip()
            password = os.getenv("JARVIS_EMAIL_PASSWORD", "")
            recipient = os.getenv("JARVIS_EMAIL_TO", "").strip()
            if not address or not password or not recipient:
                speak("Email is not configured. Please set the email environment variables.")
                return True
            speak("What should I say, sir?")
            content = input_fn() if input_fn else takeCommand(sensitive=True)
            if content is None or not content.strip():
                speak("Email cancelled because no message was recognized.")
            elif command_for(content) == "exit":
                speak("Goodbye, sir.")
                return False
            else:
                speak("Send this email to the configured recipient? Say confirm send to send it, or cancel.")
                confirmation = confirm_fn() if confirm_fn else takeCommand(sensitive=True)
                if confirmation and command_for(confirmation) == "exit":
                    speak("Goodbye, sir.")
                    return False
                if not confirmation or normalize_query(confirmation) != "confirm send":
                    speak("Email cancelled. Nothing was sent.")
                    return True
                try:
                    print("Sending email...")
                    sendEmail(recipient, content)
                except Exception as error:
                    report_error("Email delivery failed", error)
                    speak("Sorry, I could not send this email.")
                else:
                    speak("Email has been sent, sir!")
        elif command == "conversation":
            speak("I am in a relationship with wifi")
        elif command == "joke":
            speak(pyjokes.get_joke())
        else:
            print("No matching command; transcript omitted for privacy.")
            # AI output is speech only: never pass it back to command routing.
            speak(ai.reply(query) if ai is not None else "Please say the command again, sir.")
    except Exception as error:
        report_error("Command failed", error)
        speak("I could not complete that command. Please check its configuration and try again.")
    return True


def main(text_mode=False, no_tts=False, execute=False, tts_test=False):
    global speech_enabled, input_failures, calibrated_microphone, engine
    input_failures = 0
    calibrated_microphone = None
    previous_speech = speech_enabled
    speech_enabled = not no_tts
    ai = AIService.from_env()
    try:
        if not text_mode and not tts_test:
            try:
                voice_settings()
            except ValueError as error:
                # This is our own sanitized validation message, not a service error.
                print(error)
                return 2
        if tts_test:
            for text in ("Jarvis speech test one.", "Jarvis speech test two."):
                speak(text)
            handle_command("time")
            return 0
        if text_mode:
            print("Text mode: external actions " + ("enabled." if execute else "disabled (dry run)."))
        if ai.provider is not None:
            print("AI chat enabled: unmatched questions and recent session context go to the provider.")
            print("AI requests use the network even in text dry-run mode; responses are printed.")
        wishMe()
        while True:
            query = input("Command> ") if text_mode else takeCommand()
            if query is None or not query.strip():
                continue
            if text_mode:
                keep_running = handle_command(query, dry_run=not execute,
                                              input_fn=lambda: getpass.getpass("Email message (hidden)> "),
                                              ai=ai, confirm_fn=lambda: input("Confirmation> "))
            else:
                keep_running = handle_command(query, ai=ai)
            if not keep_running:
                break
    except (KeyboardInterrupt, EOFError):
        print("\nJarvis stopped.")
    finally:
        ai.clear()
        speech_enabled = previous_speech
        if engine is not None:
            try:
                engine.stop()
            except Exception as error:
                report_error("Speech engine cleanup failed", error)
            finally:
                engine = None
    return 0


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", action="store_true", help="typed commands; external actions dry-run by default")
    parser.add_argument("--no-tts", action="store_true", help="print responses without using SAPI5")
    parser.add_argument("--execute", action="store_true", help="enable external actions in text mode")
    parser.add_argument("--tts-test", action="store_true", help="three speech responses without microphone input")
    parser.add_argument("--list-microphones", action="store_true", help="list local input device names and rates (no recording)")
    args = parser.parse_args()
    if args.list_microphones:
        return list_microphones()
    if args.execute and not args.text:
        parser.error("--execute requires --text")
    if args.tts_test and (args.text or args.no_tts):
        parser.error("--tts-test cannot be combined with --text or --no-tts")
    return main(args.text, args.no_tts, args.execute, args.tts_test)


def list_microphones():
    """Explicit local inventory; names can contain personal information."""
    audio = None
    try:
        audio = sr.Microphone.get_pyaudio().PyAudio()
        print("Local input devices (names may be personal; avoid sharing this output):")
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if info.get("maxInputChannels", 0) > 0:
                print(f"{index}: {info['name']} (native rate {info['defaultSampleRate']:.0f} Hz)")
        return 0
    except Exception as error:
        report_error("Microphone inventory failed", error)
        return 1
    finally:
        if audio is not None:
            try:
                audio.terminate()
            except Exception as error:
                report_error("Microphone inventory cleanup failed", error)


if __name__ == "__main__":
    raise SystemExit(cli())
