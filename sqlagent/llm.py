from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx


class LLMUnavailable(RuntimeError):
    """Raised when the configured language-model provider cannot answer."""


LLMEventHook = Callable[[str, str], None]


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "openbmb/minicpm5:fp16",
        cache_dir: Path | None = None,
        timeout: float = 180.0,
        event_hook: LLMEventHook | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.event_hook = event_hook

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
            try:
                cache_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        self._emit("response_cached", self.model)
        return value

    def _write_cached_json(self, cache_path: Path | None, value: dict[str, Any]) -> None:
        if cache_path is None:
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
            return cached

        last_error: Exception | None = None
        self._emit("request_started", self.model)
        for attempt in range(retries + 1):
            try:
                response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
                response.raise_for_status()
                content = response.json().get("message", {}).get("content", "")
                result = self._parse_json(content)
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
            response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            content = str(response.json().get("message", {}).get("content", ""))
            self._emit("response", self.model)
            return content
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            self._emit("error", str(exc))
            raise LLMUnavailable(f"Ollama model {self.model!r} is unavailable: {exc}") from exc

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise ValueError("LLM JSON response must be an object")
        return result


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
    ) -> None:
        super().__init__(base_url, model, cache_dir, timeout, event_hook)
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
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM provider response did not contain message content")
        return content

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
            return cached

        last_error: Exception | None = None
        self._emit("request_started", self.model)
        for attempt in range(retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = self._parse_json(self._content(response))
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
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
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
        )
    if provider == "opencode_go":
        return OpenCodeGoClient(
            opencode_go_base_url,
            opencode_go_api_key,
            opencode_go_model,
            cache_dir / "opencode_go",
            event_hook=event_hook,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER {provider!r}; use litellm or opencode_go")
