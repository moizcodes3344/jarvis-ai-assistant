"""Phase 1 conversation only: no tools, file storage, or action execution."""

from dataclasses import dataclass, field
import http.client
import json
import os
import re
import socket
from typing import Protocol


INSTRUCTIONS = (
    "You are JARVIS, a conversational assistant. Answer in two or three short "
    "sentences suitable for speech, using plain text without markdown, URLs, or code. "
    "You cannot execute commands, access this computer, or send email. Never claim "
    "to have performed an action. Do not request credentials."
)
MAX_RESPONSE_BYTES = 128 * 1024


class AIError(Exception):
    """Contains only a fixed public error category, never provider error text."""


def integer_setting(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
        if not minimum <= value <= maximum:
            raise ValueError
        return value
    except ValueError:
        raise AIError("configuration") from None


@dataclass(frozen=True)
class AISettings:
    provider: str = "disabled"
    model: str = ""
    timeout: int = 15
    history_turns: int = 6
    history_chars: int = 12000
    input_chars: int = 2000
    response_chars: int = 600
    max_output_tokens: int = 256

    @classmethod
    def from_env(cls):
        provider = os.getenv("JARVIS_AI_PROVIDER", "disabled").strip().lower()
        if provider == "disabled":
            return cls()
        model = os.getenv("JARVIS_AI_MODEL", "").strip()
        if provider not in ("openai", "gemini") or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", model):
            raise AIError("configuration")
        return cls(
            provider=provider, model=model,
            timeout=integer_setting("JARVIS_AI_TIMEOUT", 15, 1, 60),
            history_turns=integer_setting("JARVIS_AI_HISTORY_TURNS", 6, 0, 20),
            history_chars=integer_setting("JARVIS_AI_HISTORY_CHARS", 12000, 1000, 40000),
            input_chars=integer_setting("JARVIS_AI_INPUT_CHARS", 2000, 100, 4000),
            response_chars=integer_setting("JARVIS_AI_RESPONSE_CHARS", 600, 100, 1000),
            max_output_tokens=integer_setting("JARVIS_AI_MAX_OUTPUT_TOKENS", 1024 if provider == "gemini" else 256, 64, 2048),
        )


class Provider(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


class OpenAIProvider:
    """Fixed HTTPS endpoint; no redirects, retries, SDK, or generated tool calls."""

    def __init__(self, settings):
        self.settings = settings

    def complete(self, messages):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise AIError("credentials")
        if any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise AIError("credentials")
        body = json.dumps({
            "model": self.settings.model, "instructions": INSTRUCTIONS,
            "input": messages, "max_output_tokens": self.settings.max_output_tokens,
            "store": False, "tools": [], "tool_choice": "none",
        }).encode("utf-8")
        connection = http.client.HTTPSConnection("api.openai.com", timeout=self.settings.timeout)
        try:
            connection.request("POST", "/v1/responses", body=body, headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            })
            response = connection.getresponse()
            if response.status in (401, 403):
                raise AIError("credentials")
            if response.status == 429:
                raise AIError("rate_limit")
            if response.status != 200:
                raise AIError("unavailable")
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise AIError("response")
            result = json.loads(data)
            if not isinstance(result, dict) or result.get("status") not in ("completed", "incomplete") or result.get("error"):
                raise AIError("response")
            if not isinstance(result.get("output"), list):
                raise AIError("response")
            texts = []
            for item in result["output"]:
                if not isinstance(item, dict):
                    raise AIError("response")
                if item.get("type") == "message" and item.get("role") == "assistant":
                    if not isinstance(item.get("content"), list):
                        raise AIError("response")
                    for part in item["content"]:
                        if not isinstance(part, dict):
                            raise AIError("response")
                        if part.get("type") == "output_text":
                            if not isinstance(part.get("text"), str):
                                raise AIError("response")
                            texts.append(part["text"])
                        elif part.get("type") == "refusal":
                            texts.append("I cannot help with that request.")
            text = " ".join(texts)
            if not text.strip():
                raise AIError("response")
            return text
        except AIError:
            raise
        except (TimeoutError, socket.timeout):
            raise AIError("timeout") from None
        except (OSError, http.client.HTTPException):
            raise AIError("network") from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise AIError("response") from None
        finally:
            connection.close()


class GeminiProvider:
    """Google's fixed HTTPS Chat Completions endpoint; text only, no tools."""

    def __init__(self, settings):
        self.settings = settings

    def complete(self, messages):
        # Never fall back to OPENAI_API_KEY or another provider's credentials.
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise AIError("credentials")
        body = json.dumps({
            "model": self.settings.model,
            "messages": [{"role": "system", "content": INSTRUCTIONS}] + messages,
            "max_tokens": self.settings.max_output_tokens,
            "reasoning_effort": "low", "stream": False,
            "tool_choice": "none",
        }).encode("utf-8")
        connection = http.client.HTTPSConnection(
            "generativelanguage.googleapis.com", timeout=self.settings.timeout
        )
        try:
            connection.request("POST", "/v1beta/openai/chat/completions", body=body, headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            })
            response = connection.getresponse()
            if response.status in (401, 403):
                raise AIError("credentials")
            if response.status == 429:
                raise AIError("rate_limit")
            if response.status != 200:
                raise AIError("unavailable")
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise AIError("response")
            result = json.loads(data)
            if not isinstance(result, dict) or result.get("error"):
                raise AIError("response")
            choices = result.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise AIError("response")
            message = choices[0].get("message")
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise AIError("response")
            # Reject tool/function calls even if an unexpected provider response includes them.
            if message.get("tool_calls") or message.get("function_call"):
                raise AIError("response")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise AIError("response")
            return content
        except AIError:
            raise
        except (TimeoutError, socket.timeout):
            raise AIError("timeout") from None
        except (OSError, http.client.HTTPException):
            raise AIError("network") from None
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            raise AIError("response") from None
        finally:
            connection.close()


def redact_credentials(text):
    # Longer secrets first so overlapping credentials cannot leave a visible suffix.
    secrets = {os.getenv(name, "").strip() for name in
               ("OPENAI_API_KEY", "GEMINI_API_KEY", "JARVIS_EMAIL_PASSWORD")}
    for secret in sorted(secrets - {""}, key=len, reverse=True):
        text = text.replace(secret, "[credential omitted]")
    return text


def voice_text(text, limit):
    text = redact_credentials(text)
    text = re.sub(r"```.*?(?:```|$)", " Code omitted. ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*#>]+|\d+[.)])\s*", "", text)
    text = re.sub(r"[*`_~]", "", text)
    text = " ".join("".join(char for char in text if char.isprintable() or char.isspace()).split())
    # Formatting can join fragments into a credential: redact again before truncation.
    text = redact_credentials(text)
    if len(text) > limit:
        text = text[:limit - 3].rsplit(" ", 1)[0] + "..."
    return text


ERROR_RESPONSES = {
    "configuration": "AI configuration is invalid. Check the provider, model, and limits. Built-in commands still work.",
    "credentials": "AI credentials are missing or rejected. Check OPENAI_API_KEY. Built-in commands still work.",
    "rate_limit": "AI is busy or its quota is exhausted. Please try again later.",
    "timeout": "AI took too long to respond. Please try again later.",
    "network": "I could not reach the AI service. Please check your connection.",
    "response": "AI returned an unusable response. Please try again later.",
    "unavailable": "AI is unavailable right now. Please try again later.",
}


@dataclass(repr=False)
class AIService:
    settings: AISettings
    provider: Provider | None = field(default=None, repr=False)
    _history: list[dict[str, str]] = field(default_factory=list, repr=False)
    _configuration_error: bool = False

    @classmethod
    def from_env(cls):
        try:
            settings = AISettings.from_env()
        except AIError:
            return cls(AISettings(), _configuration_error=True)
        providers = {"openai": OpenAIProvider, "gemini": GeminiProvider}
        provider_type = providers.get(settings.provider)
        return cls(settings, provider_type(settings) if provider_type else None)

    def clear(self):
        self._history.clear()

    def reply(self, query):
        if self._configuration_error:
            return ERROR_RESPONSES["configuration"]
        if self.provider is None:
            return "Please say the command again, sir."
        query = query.strip()
        if not query:
            return "Please ask a question."
        if len(query) > self.settings.input_chars:
            return "Please shorten your question so I can answer it."
        user_message = {"role": "user", "content": redact_credentials(query)}
        # Copy messages so even a faulty provider cannot mutate session history.
        # Environment credentials may rotate after a turn was retained.
        self._history = [dict(message, content=redact_credentials(message["content"]))
                         for message in self._history]
        messages = [dict(message) for message in self._history] + [user_message.copy()]
        try:
            answer = voice_text(self.provider.complete(messages), self.settings.response_chars)
            if not answer:
                raise AIError("response")
        except AIError as error:
            if str(error) == "credentials" and self.settings.provider == "gemini":
                return "AI credentials are missing or rejected. Check GEMINI_API_KEY. Built-in commands still work."
            return ERROR_RESPONSES.get(str(error), ERROR_RESPONSES["unavailable"])
        except Exception:
            # Never log provider bodies, headers, exception messages, or transcripts.
            return ERROR_RESPONSES["unavailable"]
        self._history.extend((user_message, {"role": "assistant", "content": answer}))
        while self._history and (
            len(self._history) > self.settings.history_turns * 2
            or sum(len(message["content"]) for message in self._history) > self.settings.history_chars
        ):
            del self._history[:2]
        return answer
