from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from sqlagent.concurrency import AdaptiveLimiter, LITELLM_LIMITER
from sqlagent.telemetry import Span, span


class LLMUnavailable(RuntimeError):
    """Raised when the configured language-model provider cannot answer."""


class LLMSchemaViolation(ValueError):
    pass


def _validate_schema(value: Any, schema: dict[str, Any] | None, path: str = "$") -> None:
    if not schema:
        return
    expected = schema.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected in matches and not matches[expected]:
        raise LLMSchemaViolation(f"LLM schema violation at {path}: expected {expected}")
    if isinstance(value, dict):
        for required in schema.get("required") or []:
            if required not in value:
                raise LLMSchemaViolation(f"LLM schema violation at {path}: missing {required}")
        properties = schema.get("properties") or {}
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{path}.{key}")
    elif isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")


LLMEventHook = Callable[[str, str], None]
_cache_writes_enabled: ContextVar[bool] = ContextVar("sqlagent_cache_writes_enabled", default=True)


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "openbmb/minicpm5:fp16",
        cache_dir: Path | None = None,
        timeout: float = 180.0,
        event_hook: LLMEventHook | None = None,
        limiter: AdaptiveLimiter | None = LITELLM_LIMITER,
        priority: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.event_hook = event_hook
        self.limiter = limiter
        self.priority = priority
        self._cache_state_lock = threading.Lock()
        self._cache_write_disable_depth = 0

    @contextmanager
    def cache_writes_disabled(self) -> Iterator[None]:
        token = _cache_writes_enabled.set(False)
        with self._cache_state_lock:
            self._cache_write_disable_depth += 1
        try:
            yield
        finally:
            with self._cache_state_lock:
                self._cache_write_disable_depth -= 1
            _cache_writes_enabled.reset(token)

    def _cache_writes_allowed(self) -> bool:
        with self._cache_state_lock:
            return _cache_writes_enabled.get() and self._cache_write_disable_depth == 0

    def _limited(self):
        from contextlib import nullcontext

        return self.limiter.slot(priority=self.priority) if self.limiter else nullcontext()

    @staticmethod
    def _prompt_meta(system: str, user: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "prompt_hash": hashlib.sha256((system + "\0" + user).encode()).hexdigest(),
            "schema_hash": (
                hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest() if schema else None
            ),
        }

    @staticmethod
    def _usage(response: httpx.Response, llm_span: Span) -> None:
        try:
            body = response.json()
        except ValueError:
            return
        usage = body.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens"):
            llm_span.attributes[key] = usage.get(key)
        choices = body.get("choices") or []
        llm_span.attributes["finish_reason"] = choices[0].get("finish_reason") if choices else None

    def _emit(self, event: str, detail: str) -> None:
        if self.event_hook:
            self.event_hook(event, detail)

    def _cache_path(self, payload: dict[str, Any]) -> Path | None:
        if self.cache_dir is None:
            return None
        cache_payload = {"cache_version": 2, **payload}
        digest = hashlib.sha256(json.dumps(cache_payload, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cached_json(self, cache_path: Path | None) -> dict[str, Any] | None:
        if cache_path is None or not cache_path.exists():
            return None
        try:
            value = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("cached LLM response must be a JSON object")
        except (OSError, TypeError, ValueError) as exc:
            self._emit("cache_invalid", f"{self.model}: {exc}")
            if self._cache_writes_allowed():
                try:
                    cache_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return None
        self._emit("response_cached", self.model)
        return value

    def _write_cached_json(self, cache_path: Path | None, value: dict[str, Any]) -> None:
        if cache_path is None or not self._cache_writes_allowed():
            return
        temporary_path: Path | None = None
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=cache_path.parent,
                prefix=f".{cache_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(value, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
            temporary_path.replace(cache_path)
        except OSError as exc:
            self._emit("cache_write_failed", str(exc))
        finally:
            if temporary_path and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def chat_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": schema or "json",
            "options": {"temperature": 0.7, "top_p": 0.95, "num_ctx": 16384},
        }
        cache_path = self._cache_path(payload)
        cached = self._read_cached_json(cache_path)
        if cached is not None:
            with span(
                "llm",
                "chat_json",
                provider="ollama",
                model=self.model,
                cache_hit=True,
                prompt_tokens=None,
                completion_tokens=None,
                reasoning_tokens=None,
                finish_reason=None,
                **self._prompt_meta(system, user, schema),
            ):
                pass
            return cached

        last_error: Exception | None = None
        self._emit("request_started", self.model)
        for attempt in range(retries + 1):
            try:
                with self._limited(), span(
                    "llm", "chat_json", provider="ollama", model=self.model, attempt=attempt + 1,
                    cache_hit=False, **self._prompt_meta(system, user, schema)
                ) as llm_span:
                    response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
                    response.raise_for_status()
                    body = response.json()
                    content = body.get("message", {}).get("content", "")
                    llm_span.attributes["prompt_tokens"] = body.get("prompt_eval_count")
                    llm_span.attributes["completion_tokens"] = body.get("eval_count")
                    llm_span.attributes["reasoning_tokens"] = None
                    llm_span.attributes["finish_reason"] = body.get("done_reason")
                result = self._parse_json(content)
                _validate_schema(result, schema)
                self._write_cached_json(cache_path, result)
                self._emit("response", self.model)
                return result
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
                if attempt < retries:
                    continue
        self._emit("error", str(last_error or "unknown Ollama error"))
        raise LLMUnavailable(f"Ollama model {self.model!r} did not return JSON: {last_error}")

    def chat_text(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.7, "top_p": 0.95, "num_ctx": 16384},
        }
        self._emit("request_started", self.model)
        try:
            with self._limited(), span(
                "llm", "chat_text", provider="ollama", model=self.model, cache_hit=False,
                **self._prompt_meta(system, user)
            ) as llm_span:
                response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
                response.raise_for_status()
                body = response.json()
                content = str(body.get("message", {}).get("content", ""))
                llm_span.attributes["prompt_tokens"] = body.get("prompt_eval_count")
                llm_span.attributes["completion_tokens"] = body.get("eval_count")
                llm_span.attributes["reasoning_tokens"] = None
                llm_span.attributes["finish_reason"] = body.get("done_reason")
            self._emit("response", self.model)
            return content
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._emit("error", str(exc))
            raise LLMUnavailable(f"Ollama model {self.model!r} is unavailable: {exc}") from exc

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        try:
            result = json.loads(cleaned)
        except ValueError:
            result = _extract_embedded_json(cleaned)
        if not isinstance(result, dict):
            raise ValueError("LLM JSON response must be an object")
        return result


def _extract_embedded_json(text: str) -> Any:
    """Salvage a JSON object embedded in prose, fences, or reasoning chatter.

    Models without enforced structured output often wrap the payload in
    explanation text; scan every ``{`` as a potential start and return the
    first complete value that parses.
    """
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            result, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(result, dict):
            return result
    raise ValueError("no JSON object found in LLM response")


class OpenCodeGoClient(OllamaClient):
    """OpenCode Go client using its OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        cache_dir: Path | None = None,
        timeout: float = 180.0,
        event_hook: LLMEventHook | None = None,
        limiter: AdaptiveLimiter | None = LITELLM_LIMITER,
        priority: int = 0,
    ) -> None:
        super().__init__(base_url, model, cache_dir, timeout, event_hook, limiter, priority)
        self.api_key = api_key.strip()

    provider_label = "OpenCode Go"
    api_key_env = "OPENCODE_GO_API_KEY"
    cache_provider = "opencode_go"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _cache_path(self, payload: dict[str, Any]) -> Path | None:
        # Keep provider caches isolated when the same model name is used locally and remotely.
        return super()._cache_path({"provider": self.cache_provider, "base_url": self.base_url, **payload})

    def _ensure_key(self) -> None:
        if not self.api_key:
            message = f"{self.api_key_env} is not configured"
            self._emit("error", message)
            raise LLMUnavailable(message)

    @staticmethod
    def _content(response: httpx.Response) -> str:
        choices = response.json().get("choices", [])
        if not choices or not isinstance(choices[0], dict):
            raise ValueError("LLM provider response did not contain choices")
        message = choices[0].get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, str) and content.strip():
            return content
        # Reasoning-style models may put the whole answer into a reasoning field
        # and leave content empty: vLLM uses "reasoning", LiteLLM normalizes it
        # to "reasoning_content" — accept both.
        if isinstance(message, dict):
            for key in ("reasoning_content", "reasoning"):
                reasoning = message.get(key) or ""
                if isinstance(reasoning, str) and reasoning.strip():
                    return reasoning
        raise ValueError("LLM provider response did not contain message content")

    @staticmethod
    def _http_error(exc: httpx.HTTPStatusError) -> RuntimeError:
        detail = ""
        if exc.response is not None:
            detail = exc.response.text.strip().replace("\n", " ")[:500]
            detail = re.sub(r"(?i)(authorization|api[-_ ]?key|token)\s*[:=]\s*[^,\s]+", r"\1=[REDACTED]", detail)
        suffix = f"; provider_response={detail}" if detail else ""
        return RuntimeError(f"{exc}{suffix}")

    def chat_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        retries: int = 2,
    ) -> dict[str, Any]:
        self._ensure_key()
        system_prompt = system
        if schema:
            system_prompt += "\nReturn JSON matching this schema:\n" + json.dumps(schema, ensure_ascii=False)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user}],
            "stream": False,
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 16384,
        }
        cache_path = self._cache_path(payload)
        cached = self._read_cached_json(cache_path)
        if cached is not None:
            with span(
                "llm",
                "chat_json",
                provider=self.cache_provider,
                model=self.model,
                cache_hit=True,
                prompt_tokens=None,
                completion_tokens=None,
                reasoning_tokens=None,
                finish_reason=None,
                **self._prompt_meta(system_prompt, user, schema),
            ):
                pass
            return cached

        last_error: Exception | None = None
        self._emit("request_started", self.model)
        for attempt in range(retries + 1):
            try:
                with self._limited(), span(
                    "llm", "chat_json", provider=self.cache_provider, model=self.model, attempt=attempt + 1,
                    cache_hit=False, **self._prompt_meta(system_prompt, user, schema)
                ) as llm_span:
                    response = httpx.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    self._usage(response, llm_span)
                result = self._parse_json(self._content(response))
                _validate_schema(result, schema)
                self._write_cached_json(cache_path, result)
                self._emit("response", self.model)
                return result
            except httpx.HTTPStatusError as exc:
                last_error = self._http_error(exc)
                if exc.response is not None and 400 <= exc.response.status_code < 500:
                    break
                if attempt < retries:
                    continue
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                last_error = exc
                if attempt < retries:
                    continue
        self._emit("error", str(last_error or f"unknown {self.provider_label} error"))
        raise LLMUnavailable(f"{self.provider_label} model {self.model!r} did not return JSON: {last_error}")

    def chat_text(self, system: str, user: str) -> str:
        self._ensure_key()
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 16384,
        }
        self._emit("request_started", self.model)
        try:
            with self._limited(), span(
                "llm", "chat_text", provider=self.cache_provider, model=self.model, cache_hit=False,
                **self._prompt_meta(system, user)
            ) as llm_span:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                self._usage(response, llm_span)
                content = self._content(response)
            self._emit("response", self.model)
            return content
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._emit("error", str(exc))
            raise LLMUnavailable(f"{self.provider_label} model {self.model!r} is unavailable: {exc}") from exc

    def list_models(self) -> list[dict[str, Any]]:
        """Fetch the provider catalog only when explicitly requested by an API caller."""
        self._ensure_key()
        try:
            response = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=15.0)
            response.raise_for_status()
            data = response.json().get("data", [])
            if not isinstance(data, list):
                raise ValueError("LLM provider model catalog is not a list")
            return [item for item in data if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise LLMUnavailable(f"{self.provider_label} model catalog is unavailable: {exc}") from exc


class LiteLLMClient(OpenCodeGoClient):
    """LiteLLM proxy client using its OpenAI-compatible chat completions API."""

    provider_label = "LiteLLM"
    api_key_env = "LITELLM_API_KEY"
    cache_provider = "litellm"


def build_llm(
    *,
    provider: str,
    ollama_base_url: str,
    ollama_model: str,
    opencode_go_base_url: str,
    opencode_go_api_key: str,
    opencode_go_model: str,
    litellm_base_url: str,
    litellm_api_key: str,
    litellm_model: str,
    cache_dir: Path,
    event_hook: LLMEventHook | None = None,
    priority: int = 0,
) -> OllamaClient:
    if provider == "ollama":
        # Ollama is temporarily disabled; use the LiteLLM proxy instead.
        raise ValueError("LLM_PROVIDER 'ollama' is temporarily disabled; use litellm")
    if provider == "litellm":
        return LiteLLMClient(
            litellm_base_url,
            litellm_api_key,
            litellm_model,
            cache_dir / "litellm",
            event_hook=event_hook,
            priority=priority,
        )
    if provider == "opencode_go":
        return OpenCodeGoClient(
            opencode_go_base_url,
            opencode_go_api_key,
            opencode_go_model,
            cache_dir / "opencode_go",
            event_hook=event_hook,
            priority=priority,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER {provider!r}; use litellm or opencode_go")
