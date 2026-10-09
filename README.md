# JARVIS v0.3 — AI Brain (Phase 1.1: Gemini Integration)

A Windows Python voice-assistant prototype with a stable core: microphone input,
Google speech recognition, spoken responses, and a small set of keyword commands.
Optional AI conversation adds bounded session context to the v0.2.1 core.
There is no wake word, persistent memory, autonomous control, or GUI.

## Implemented features

- Time-based greeting and current local time.
- Two-sentence Wikipedia summaries.
- YouTube, Google, and Stack Overflow browser shortcuts.
- Plays the first supported audio file (alphabetically) from a configured folder.
- Opens a configured Visual Studio Code executable.
- Jokes and a humorous response to “are you single”.
- Optional Gmail SMTP email through the “email to Raj” command.
- Clean “exit”, “quit”, and Ctrl+C shutdown.
- Recoverable speech, device, service, configuration, and command failures.

## Requirements and installation

Windows, Python 3.12 (the inspected working environment uses 3.12.10), a microphone,
speakers, and internet access for speech recognition, Wikipedia, websites, and email.
SAPI5 is Windows-specific. Other Python versions are not verified.

From the Git repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py
```

No activation is required with these commands. Optional activation:
`.\.venv\Scripts\Activate.ps1`. If PowerShell blocks activation, use the explicit
interpreter commands above. Do not overwrite an existing working environment.
PyAudio is required by SpeechRecognition's microphone input. If pip cannot find
a compatible Windows wheel, check Python version and architecture; use Python
3.12 rather than installing binaries from untrusted sites. No `pywhatkit` is needed.

## Microphone and supported commands

Enable Windows microphone access for desktop apps and check the input device in
Windows sound settings. The assistant uses the Windows default input device and its native sample rate.
To select the Windows default explicitly:

```powershell
$env:JARVIS_MIC_DEVICE_INDEX = 'default'
.\.venv\Scripts\python.exe -c "import speech_recognition as sr; print(list(enumerate(sr.Microphone.list_microphone_names())))"
```

Use a listed numeric index if needed. To restore the original audio settings, set
`JARVIS_MIC_DEVICE_INDEX=1` and `JARVIS_MIC_SAMPLE_RATE=44100`.
Stay quiet during the one-second calibration before the first listening cycle.
Calibration repeats when device settings change; dynamic energy adjustment stays
enabled by default. Recognition defaults to `en-in` for compatibility, but language,
pause threshold, calibration, and listening limits are configurable below. Listening
defaults to five seconds to start speech and ten seconds per phrase. Failures back
off for 1, 2, 4, then 8 seconds, capped at 8; successful recognition resets the delay.
A 0.3-second delay before capture helps avoid the tail of spoken responses. Google
recognition defaults to a ten-second operation timeout. Very short phrases now use
a 0.2-second detection threshold.

Examples: “What's the time?”, “Open YouTube”, “Open Google”, “Open Stack Overflow”,
“Wikipedia Albert Einstein”, “Play music”, “Open code”, “Tell me a joke”,
“Are you single?”, “Email to Raj”, “Exit”, “Quit”. Time also accepts “What is the time”,
“Tell me the time”, and “Time”. Matching normalizes case, punctuation, and whitespace
and uses word boundaries. Unmatched input reaches AI when explicitly configured; otherwise it requests a repeat.
Email asks for one message and then requires the exact phrase `confirm send`
before sending to the configured recipient. Other replies or recognition failures cancel delivery. “Exit” or “Quit” at that prompt also shuts down.

## Configuration and security

Set environment variables in the same terminal before running:

```powershell
$env:JARVIS_MUSIC_DIR = 'C:\Users\YOUR_USER\Music'
$env:JARVIS_CODE_PATH = 'C:\PATH\TO\Code.exe'
```

| Variable | Default / purpose |
| --- | --- |
| `JARVIS_MIC_DEVICE_INDEX` | `default`; integer device index or `default` |
| `JARVIS_MIC_SAMPLE_RATE` | Unset; native device rate, or a positive integer such as `44100` |
| `JARVIS_DEBUG` | Off; `1`, `true`, or `yes` enables stages, route IDs, thresholds and retry counts; never transcripts |
| `JARVIS_MUSIC_DIR` | Unset; folder containing audio files |
| `JARVIS_CODE_PATH` | Unset; VS Code executable path |
| `JARVIS_EMAIL_ADDRESS` | Unset; Gmail sender/login address |
| `JARVIS_EMAIL_PASSWORD` | Unset; Gmail app password where account policy permits |
| `JARVIS_EMAIL_TO` | Unset; recipient for “email to Raj” |

Missing optional settings produce a useful response; other commands remain usable.
The root `.env.example` is a placeholder reference. **The program does not load
`.env` files automatically**; export values using your shell or a trusted launcher.
Do not paste real passwords into source, examples, Git, or shared terminal logs.
Both ignore files exclude `.env`, local environments, caches, and logs. Rotate any
credential you accidentally publish; ignoring a file does not remove Git history.
Original email values were placeholders, not verified leaked credentials.
Error diagnostics show context and exception type without raw exception messages
or recognized transcripts. Debug mode also omits transcripts, device names,
credentials, and dictated email bodies. Typed commands may be echoed by your
terminal; the typed email body prompt is hidden. No diagnostic log file is created. Assistant responses are printed for verification. Audio is sent to Google's recognition service: avoid
dictating sensitive information. Email uses TLS and a ten-second SMTP timeout.

## Project structure

```text
repository/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
└── JARVIS.PY/
    ├── JARVIS2.0.py          # Assistant entry point and command loop
    ├── ai_service.py         # Conversation service and HTTPS provider adapter
    ├── mic_test.py           # Standalone microphone capture diagnostic
    ├── jarvisreadme.md       # Legacy documentation pointer
    ├── tests/test_stable_core.py
    ├── tests/test_ai_service.py
    └── .gitignore
```

## Troubleshooting and limitations

- Input errors: check microphone permissions, device index, PyAudio installation,
  and any explicitly configured sample rate. Stay quiet during calibration. Use Ctrl+C to stop repeated failures.
- Recognition unavailable: check connectivity. Silence and unintelligible speech
  return to listening without terminating the assistant.
- Wikipedia: try a specific topic for ambiguity or missing pages. Library/network
  exceptions (including JSON/API failures) are handled. A narrow compatibility
  wrapper for `wikipedia` 1.4.0 uses HTTPS and three-second connect/five-second read
  timeouts, restoring library state after each synchronous lookup. These are per
  HTTP request, not a total lookup deadline; multiple requests or slow trickling
  responses can take longer. This wrapper would need review before adding concurrency.
- No spoken audio: check Windows voices and output device. Speech errors fall back
  to printed responses. The SAPI5 loop pumps events through pyttsx3's public external
  loop API and checks completion, cancellation, and error callbacks; repeated
  `runAndWait()` in installed pyttsx3 2.99 cancelled subsequent utterances.
  Speech pumping has a 15–120 second deadline based on response length, but a
  blocking native driver call cannot be interrupted by that deadline.
  Missing dependencies must be installed before startup.
- Music/VS Code: verify the configured paths and Windows file associations.
- Email: check sender, recipient, app-password eligibility, and SMTP access.
  Failed dictation cancels sending. Delivery failures return to listening.
- `mic_test.py` retains its original device-1 capture/calibration diagnostic and may
  raise on timeout/device errors; it is not the assistant's protected input loop.
- Commands use normalized phrases and word boundaries, not natural-language intent reasoning.
  Email dictation is limited to one phrase (ten seconds by default). Voice services and device
  drivers can still stall; this prototype has no background cancellation system.

## Validation

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m py_compile .\JARVIS.PY\JARVIS2.0.py .\JARVIS.PY\mic_test.py
.\.venv\Scripts\python.exe -m unittest discover -s .\JARVIS.PY\tests -v
```

Tests mock microphone, speech, browser, and external-service behavior. They do not
prove actual microphone capture, SAPI5 playback, online recognition, Wikipedia
availability, browser launch, local app launch, or email delivery. Manually check
greeting, time, browser commands, silence, unclear speech, offline behavior, and
exit/quit on your machine before treating v0.2.1 as hardware-validated.

## Roadmap (planned)

v0.3 Phase 1 implements optional conversation only. Later phases may add
intent reasoning, a reviewed tool system, the “Jarvis” wake word, controlled memory,
a desktop GUI, packaging, and broader integration tests. These remain unimplemented.

## Independent TTS smoke check

From the repository root, run this without opening a microphone:

```powershell
$env:JARVIS_DEBUG = '1'
.\.venv312\Scripts\python.exe -c "import runpy; j=runpy.run_path('JARVIS.PY/JARVIS2.0.py'); j['speak']('Speech test one'); j['speak']('Speech test two'); j['handle_command']('time')"
Remove-Item Env:JARVIS_DEBUG
```

Use your chosen environment's interpreter if it is named differently. All three
responses should print and be audible. Driver completion diagnostics do not prove
that speakers are unmuted. Next run the full assistant, stay quiet during calibration,
then try time variations, browser commands, an unknown command, silence, Wikipedia,
and quit/exit. Keep email unset during the initial smoke test to avoid sending mail.


## v0.2.1 audio tuning

Export settings in the same PowerShell terminal; `.env` is still a reference only.
Numeric settings are validated. Invalid voice input settings stop startup with a
sanitized message and exit status 2; TTS configuration errors fall back to text.
Restart after changing settings. No automatic accent guessing or repeated language
fallback requests are made. Choose the recognition language that fits your speech:

```powershell
$env:JARVIS_RECOGNITION_LANGUAGE = 'en-GB'  # examples: en-US, en-IN, en-GB
$env:JARVIS_DEBUG = '1'                   # stages/outcomes; no transcripts
```

| Variable | Default | Accepted range / purpose |
| --- | --- | --- |
| `JARVIS_RECOGNITION_LANGUAGE` | `en-in` | Google language tag; no fixed accent requirement |
| `JARVIS_LISTEN_TIMEOUT` | 5 | 1–60 seconds to begin speech |
| `JARVIS_PHRASE_TIME_LIMIT` | 10 | 1–60 seconds per phrase |
| `JARVIS_RECOGNITION_TIMEOUT` | 10 | 1–60 seconds for recognition service operations |
| `JARVIS_MIC_CHUNK_SIZE` | 1024 | 128–8192 frames |
| `JARVIS_CALIBRATION_DURATION` | 1 | 0–5 seconds; 0 disables calibration |
| `JARVIS_ENERGY_THRESHOLD` | 300 | 1–10000; initial threshold, before calibration |
| `JARVIS_DYNAMIC_ENERGY` | true | true/false; automatic threshold adaptation |
| `JARVIS_PAUSE_THRESHOLD` | 1 | 0.3–3 seconds of silence to finish a phrase |
| `JARVIS_PHRASE_THRESHOLD` | 0.2 | 0.05–3 seconds; minimum phrase duration |
| `JARVIS_AUDIO_SETTLE_TIME` | 0.3 | 0–3 seconds before opening the microphone |
| `JARVIS_RETRY_DELAY` | 1 | 0.5–10 seconds; initial failed-input delay |
| `JARVIS_MAX_RETRY_DELAY` | 8 | 1–30 seconds; caps exponential backoff |
| `JARVIS_TTS_VOICE_INDEX` | 0 | Index of an installed SAPI5 voice |
| `JARVIS_TTS_RATE` | 200 | 80–350 words per minute |
| `JARVIS_TTS_VOLUME` | 1 | 0–1; 0 deliberately mutes speech |

Calibration occurs once per device/calibration configuration. Stay quiet during it;
speaking during calibration can set the threshold too high. If noise changes,
restart to recalibrate. To try a fixed threshold, disable dynamic adjustment AND
calibration, then tune the threshold locally. Do not use an arbitrary copied value
without checking your microphone. The Windows default can change after plugging
in a headset; use an explicit input index if needed. To inspect input devices only:

```powershell
.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py --list-microphones
```

This explicit inventory prints local device names, which may contain personal
information; avoid sharing it publicly. It does not record audio. The built-in
`mic_test.py` remains a legacy device-1 diagnostic; use the assistant's settings
for reliability testing.

`WaitTimeoutError` means speech did not cross the detection threshold in time.
`UnknownValueError` means audio was captured but the service could not decode it;
it does not prove the command router failed. `RequestError` means recognition
service access failed. Check Windows microphone level, chosen input, quiet-room
calibration, language, and connectivity in that order. The third consecutive failure
prints tuning guidance; no automatic audio recordings or transcript files are saved.
For silent TTS, check Windows Volume Mixer, default output, installed SAPI5 voices,
and `JARVIS_TTS_VOLUME`. The existing public SAPI5 loop is retained; callbacks
confirm synthesis completion, not audible output at your speakers.

## Safe text-command mode and manual verification

From the repository root, using the existing Python 3.12 environment:

```powershell
.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py --text --no-tts
```

This opens no microphone, initializes no speech engine, and uses the real router.
Time, jokes, conversational responses and exit execute locally. Wikipedia, browser,
music, application and email commands report their matched route as a dry run.
No shell command strings or Python code are executed from typed input.
`--text` alone additionally uses speech playback. To deliberately enable the existing
external actions, add `--execute`; configured email prompts for confirmation after message input,
as in voice mode, only after the exact `confirm send` confirmation. Leave email unconfigured initially.
EOF and Ctrl+C exit cleanly. Supported equivalents now also include “what time is it”,
“current time”, “launch YouTube”, “open up Google”, “start VS Code”, and “please quit”.

1. Run `--text --no-tts`. Enter `what's the time`, `what time is it`, `open youtube`,
   `wikipedia albert einstein`, `unknown command`, then `quit`. Confirm time output,
   dry-run routes, an unknown-command notice, and a clean terminal return.
2. Run `.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py --tts-test`.
   Confirm that BOTH test sentences and the time are audible. Repeat the command.
   Completion messages alone do not count as successful audible-playback tests.
3. Run `--list-microphones`, choose an input if the Windows default is unsuitable,
   and set `JARVIS_RECOGNITION_LANGUAGE` to your preferred tag.
4. Run the assistant without flags. Stay quiet during calibration, wait for
   `Listening...`, then say the time variations, a joke, and “open YouTube”.
   Check spoken responses and actual browser opening. Test quit and exit separately.
5. Remain silent through several cycles; check capped retries. Try unclear speech
   and temporarily disconnect the network; verify recovery and Ctrl+C shutdown.
6. Try Wikipedia (success, ambiguous topic, missing topic, and unavailable service),
   then time to confirm the assistant remains usable. Local app/music launches and
   email delivery need separate manual checks with safe configuration.

Hardware and network reliability remain pending YOUR confirmation. Automated mocks,
CLI smoke checks, and SAPI5 completion events do not verify microphone accuracy or
speaker audibility. Network timeouts remain per operation/request, not a universal
wall-clock deadline, and native device/driver calls can still block.


## v0.3 Phase 1.1: optional AI conversation

AI is disabled by default, so existing command and audio behavior remains usable
without a key. Phase 1.1 supports `JARVIS_AI_PROVIDER=disabled`, `openai`, or
`gemini`; other providers are rejected safely. Separate provider adapters in
`ai_service.py` keep microphone, routing, and TTS code independent of the API protocol. No packages were
added; the adapter uses Python's standard-library HTTPS client.

For OpenAI, select a text model available to your API account that supports the Responses API.
There is deliberately no assumed model ID. Export configuration in the same terminal
before launching; neither `.env.example` nor `.env` is automatically loaded:

```powershell
$env:JARVIS_AI_PROVIDER = 'openai'
$env:JARVIS_AI_MODEL = 'YOUR_RESPONSES_MODEL_ID'  # replace with your chosen model ID
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'API key' -AsSecureString)).Password
.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py --text --no-tts
```

Use your existing environment's interpreter if named differently. The hidden prompt
keeps the key out of typed command history. Never paste keys into source, logs, or
Git. Model availability, pricing, and API quota depend on your account. No real
provider request was made during implementation. The adapter follows the
[official Responses API reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

| Variable | Default | Accepted range / purpose |
| --- | --- | --- |
| `JARVIS_AI_PROVIDER` | `disabled` | `disabled`, `openai`, or `gemini`; explicit network opt-in |
| `JARVIS_AI_MODEL` | Empty | Required when enabled; supported provider model ID, e.g. `gemini-3.8-flash` |
| `OPENAI_API_KEY` | Empty | OpenAI-only credential, read at request time |
| `GEMINI_API_KEY` | Empty | Gemini-only credential; no fallback to the OpenAI key |
| `JARVIS_AI_TIMEOUT` | 15 | 1–60 seconds per blocking network operation |
| `JARVIS_AI_HISTORY_TURNS` | 6 | 0–20 completed exchanges; 0 disables history |
| `JARVIS_AI_HISTORY_CHARS` | 12000 | 1000–40000 retained history characters |
| `JARVIS_AI_INPUT_CHARS` | 2000 | 100–4000 characters per question; longer input is rejected locally |
| `JARVIS_AI_RESPONSE_CHARS` | 600 | 100–1000 displayed/spoken characters |
| `JARVIS_AI_MAX_OUTPUT_TOKENS` | OpenAI: 256; Gemini: 1024 | 64–2048 generated tokens; applies to thinking and visible output |

Restart after changing settings. Invalid AI settings or missing/rejected credentials
affect AI only: built-in commands remain usable. Rate limits, quota errors, network
failures, timeouts, malformed output, and empty output produce short public messages.
There are no automatic retries or background tasks. HTTP response reads are capped
at 128 KiB. Network timeouts are per operation, not a strict total wall-clock deadline;
DNS lookup and slow trickling responses can still take longer.

Routing and security:

- The existing `command_for()` allowlist runs first. Matched commands, including
  dry-run commands, never reach AI or conversation history. Phrase matching remains
  the v0.2.1 behavior; Phase 1 does not use AI to infer actions.
- AI replies go only to the existing `speak()` output. No response is routed again,
  evaluated, executed as code, or interpreted as a shell command. No tools are
  supplied to the model. Browser/music/VS Code commands still require a recognized
  user command; text mode requires `--execute`. Email additionally requires exact
  `confirm send` confirmation in either mode. Confirmation input never reaches AI.
- Unmatched questions and bounded recent successful exchanges go to your selected
  provider over HTTPS. Enabling AI allows network requests even when text external actions are in
  dry-run mode. The fixed endpoint accepts no redirects or configurable proxy URL.
- History lives only in the current process session, drops oldest complete exchanges
  to satisfy both bounds, and is cleared on shutdown. Failed requests are excluded.
  A request contains retained history plus one bounded current question and fixed
  instructions. No private transcript files, personal memory, or provider conversation
  IDs are created. OpenAI requests use `store=false`; Gemini requests omit that
  OpenAI-specific field. Neither adapter promises zero provider retention. Consult your provider/account data policies before sending private content.
- Diagnostics omit questions, provider error bodies, exception details, and headers.
  Known OpenAI, Gemini, and email credentials are redacted from AI input,
  formatted output, console/TTS responses, and diagnostic messages. This is not a
  general sensitive-data detector. Assistant replies are printed and may repeat user
  content; typed questions may be echoed by the terminal. Voice input still uses
  Google's speech recognition service. Avoid sensitive questions or shared consoles.
- Responses request short plain text, remove code blocks, links and common Markdown,
  collapse whitespace, and enforce a character cap before SAPI5 playback. AI can be
  wrong; Phase 1 has no live research or action capability.

Validation and manual checks from the repository root:

```powershell
.\.venv312\Scripts\python.exe -m py_compile .\JARVIS.PY\JARVIS2.0.py .\JARVIS.PY\ai_service.py .\JARVIS.PY\mic_test.py
.\.venv312\Scripts\python.exe -m unittest discover -s .\JARVIS.PY\tests -v
git diff --check
```

The AI tests mock the HTTPS transport and provider. They verify the request contract,
command priority, text/voice integration, history bounds and cleanup, failure recovery,
credential privacy, non-execution of AI output, and email confirmation. They are not
real provider tests and do not prove account/model compatibility or hardware behavior.

1. With AI configured, run `--text --no-tts`, ask `Explain gravity briefly`, then
   `Explain that more simply`. Check concise output and follow-up context. Enter
   `time`, `open youtube`, and `quit`; check local time, browser dry run, and clean exit.
2. Restart, ask about the prior conversation, and verify context was cleared. Set
   `JARVIS_AI_HISTORY_TURNS=0` to verify independent questions. Real AI responses are
   nondeterministic and may guess; automated tests verify clearing directly.
3. Remove the selected provider's key (`OPENAI_API_KEY` or `GEMINI_API_KEY`)
   in a test terminal and ask a question; check the credential
   message, then `time`. Test disconnected network behavior and recovery separately.
4. Run `--text` to hear AI replies, then run without flags to test microphone,
   recognition, follow-up context, repeated SAPI5 playback, and `quit`. Existing
   hardware and service checks above still apply.
5. With safe email configuration, use `--text --execute`; confirm that `cancel` sends
   nothing and `confirm send` authorizes delivery. Actual delivery is a separate,
   explicit manual test. Do not use production recipients for smoke checks.

Disable AI and remove the session credential when finished:

```powershell
$env:JARVIS_AI_PROVIDER = 'disabled'
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
```


## Gemini setup and manual verification

Phase 1.1 adds `GeminiProvider` with the fixed HTTPS Chat Completions REST endpoint:
`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`.
No endpoint environment variable is accepted, redirects are rejected, and no extra
packages are required. The existing OpenAI Responses adapter remains unchanged.
Use a Gemini API key from Google AI Studio with `GEMINI_API_KEY`; do not put it in
`OPENAI_API_KEY`, which sends credentials to OpenAI.

Google lists `gemini-3.8-flash` as a stable text-output model and uses it in the
[official compatibility examples](https://ai.google.dev/gemini-api/docs/openai).
See the [model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
for current capabilities. Account availability and live behavior have not been tested.
This integration continues to use existing speech recognition and SAPI5; it does not
use Gemini's audio APIs, computer control, tools, or persistent personal memory.

From the repository root in PowerShell, using the existing environment:

```powershell
$env:JARVIS_AI_PROVIDER = 'gemini'
$env:JARVIS_AI_MODEL = 'gemini-3.8-flash'
$env:JARVIS_AI_MAX_OUTPUT_TOKENS = '1024'
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Gemini API key' -AsSecureString)).Password

# Text-only chat: no microphone or SAPI5; existing external actions stay in dry run.
.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py --text --no-tts

# Typed questions with SAPI5 output.
.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py --text

# Existing microphone/recognition pipeline and SAPI5 output.
.\.venv312\Scripts\python.exe .\JARVIS.PY\JARVIS2.0.py
```

AI uses the network even in text dry-run mode and may incur charges. The key prompt
is hidden and keeps its value out of typed command history. Settings are process
environment variables, not persisted to files. Never print or share the credential.
Voice mode retains the existing user-command external actions and email confirmation.

1. In text-only mode, ask `Explain gravity briefly`, then `Explain that more simply`.
   Check concise output and follow-up context. Enter `time`, `open youtube`, and `quit`;
   check local time, a browser dry run, and a clean exit.
2. Restart to verify a fresh conversation; use `JARVIS_AI_HISTORY_TURNS=0` if you want
   no retained exchanges. Automated tests verify actual state clearing; live models
   can guess even without context.
3. Remove `GEMINI_API_KEY` in a test terminal and ask a question. Check that the error
   names `GEMINI_API_KEY`, then ask `time` to confirm command recovery. Do not use real
   keys as test questions. Test network outages separately.
4. Run `--text` and then voice mode. Confirm audible repeated SAPI5 responses,
   microphone calibration, recognition, a follow-up question, and `quit`.

The Gemini request prepends the fixed instructions as a system message, then sends
bounded session history and the current question. It uses `reasoning_effort=low`,
non-streaming output, `tool_choice=none`, and a `max_tokens` limit. Only non-empty
string content from the first assistant choice is accepted. Tool/function calls,
malformed output, and empty output are rejected safely. A small token budget may
leave no visible answer after thinking; increase the configured limit up to 2048
for your manual test if needed. No automatic retries incur extra requests.

All 58 pre-existing tests remain intact. The full suite now has **76 passing tests**,
including 18 mocked Gemini transport, privacy, TTS, routing, and failure checks. Real
provider requests, model-account compatibility, microphone capture and SAPI5
audibility remain manual verification; mocks do not establish those results.

When finished:

```powershell
$env:JARVIS_AI_PROVIDER = 'disabled'
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:JARVIS_AI_MAX_OUTPUT_TOKENS -ErrorAction SilentlyContinue
```
