# JARVIS quality roadmap

Baseline: clean `main` at `ee485af`; Python 3.12 on Windows, unittest,
standard-library HTTPS AI adapters, SpeechRecognition, pyttsx3/SAPI5,
Wikipedia, pyjokes and optional Gmail SMTP. No existing CI or lint configuration.
Preserve the command allowlist, explicit AI opt-in, email confirmation and dry runs.

## Prioritized first batch

1. Reject malformed OpenAI response structures with sanitized errors.
2. Re-redact retained AI history when credentials change during a session.
3. Validate email envelope configuration before opening SMTP connections.
4. Cancel blank email dictation before requesting send confirmation.
5. Reset stopped TTS engines so subsequent sessions initialize cleanly.
6. Make the microphone diagnostic safe to import without opening hardware.
7. Provide local command help without sending help requests to AI.
8. Allow explicit conversation reset without restarting the assistant.
9. Add a dependency-free repository validation command, including syntax,
   formatting hygiene and credential-pattern checks with redacted diagnostics.
10. Add least-privilege Windows Python 3.12 CI for validation and mocked tests.
11. Document the final behavior, validation procedure and remaining limitations.

Each implementation gets focused regression tests, an exact diff review and
its own meaningful commit. The roadmap is a planning artifact, not a promise of
100 commits. Split by independently useful behavior, never by arbitrary counts.

## Follow-up investigations (not automatic implementation)

- Test real microphone/SAPI5 behavior on supported Windows devices.
- Verify provider/account compatibility using separately authorized live tests.
- Evaluate optional audio dependencies and a portable text-only install path.
- Profile music directory enumeration before replacing it.
- Consider a packaging/module layout only when installation needs justify migration.
- Evaluate a formatter/type checker once development dependency policy is agreed.
- Review dependency advisories and upgrade compatibility in a separate batch.
- Consider stricter command intent parsing without breaking documented phrases.
- Add integration failure tests when concrete gaps appear.

Do not add wake-word capture, autonomous tools, paid services or persistent
personal data as incidental quality work. Hardware and live services are not
validated by mocked tests. Existing commit identities remain unchanged.
