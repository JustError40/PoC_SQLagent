from pathlib import Path

import httpx

from sqlagent.config import Settings
from sqlagent.llm import OpenCodeGoClient, build_llm


def test_build_llm_selects_opencode_go(tmp_path: Path) -> None:
    settings = Settings(
        llm_provider="opencode_go",
        opencode_go_base_url="https://opencode.ai/zen/go/v1",
        opencode_go_api_key="secret",
        opencode_go_model="deepseek-v4-flash",
    )

    client = build_llm(
        provider=settings.llm_provider,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        opencode_go_base_url=settings.opencode_go_base_url,
        opencode_go_api_key=settings.opencode_go_api_key,
        opencode_go_model=settings.opencode_go_model,
        litellm_base_url=settings.litellm_base_url,
        litellm_api_key=settings.litellm_api_key,
        litellm_model=settings.litellm_model,
        cache_dir=tmp_path,
    )

    assert isinstance(client, OpenCodeGoClient)
    assert client.model == "deepseek-v4-flash"
    assert client.base_url.endswith("/v1")


def test_opencode_go_chat_json_uses_bearer_and_openai_shape(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"sql":"SELECT 1"}'}}]}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenCodeGoClient(
        "https://opencode.ai/zen/go/v1",
        "secret-key",
        "deepseek-v4-flash",
        cache_dir=tmp_path,
    )

    result = client.chat_json("Return SQL", "question", retries=0)

    assert result == {"sql": "SELECT 1"}
    assert captured["url"] == "https://opencode.ai/zen/go/v1/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["response_format"] == {"type": "json_object"}


def test_opencode_go_without_key_fails_before_network(tmp_path: Path) -> None:
    client = OpenCodeGoClient("https://opencode.ai/zen/go/v1", "", "deepseek-v4-flash", tmp_path)

    try:
        client.chat_text("system", "user")
    except Exception as exc:
        assert "OPENCODE_GO_API_KEY" in str(exc)
    else:
        raise AssertionError("missing OpenCode Go key must fail explicitly")


def test_invalid_cache_is_discarded_and_request_continues(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"sql":"SELECT 1"}'}}]}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenCodeGoClient(
        "https://opencode.ai/zen/go/v1", "secret-key", "deepseek-v4-flash", cache_dir=tmp_path
    )
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "system", "content": "Return SQL"}, {"role": "user", "content": "question"}],
        "stream": False,
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 16384,
    }
    cache_path = client._cache_path(payload)
    assert cache_path is not None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{broken", encoding="utf-8")

    assert client.chat_json("Return SQL", "question", retries=0) == {"sql": "SELECT 1"}
    assert cache_path.read_text(encoding="utf-8").strip() == '{\n  "sql": "SELECT 1"\n}'


def _client_with_fake_response(monkeypatch, tmp_path: Path, message: dict[str, object]) -> OpenCodeGoClient:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": message}]}

    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: FakeResponse())
    return OpenCodeGoClient("https://opencode.ai/zen/go/v1", "secret-key", "deepseek-v4-flash", cache_dir=tmp_path)


def test_chat_json_salvages_json_wrapped_in_prose_and_fence(monkeypatch, tmp_path: Path) -> None:
    client = _client_with_fake_response(
        monkeypatch,
        tmp_path,
        {"content": 'Sure! Here is the fix:\n```json\n{"sql": "SELECT 1"}\n```\nHope that helps.'},
    )

    assert client.chat_json("Return SQL", "question", retries=0) == {"sql": "SELECT 1"}


def test_chat_json_salvages_bare_json_inside_text(monkeypatch, tmp_path: Path) -> None:
    client = _client_with_fake_response(
        monkeypatch,
        tmp_path,
        {"content": 'The corrected query is {"sql": "SELECT 2"} as shown.'},
    )

    assert client.chat_json("Return SQL", "question", retries=0) == {"sql": "SELECT 2"}


def test_chat_json_falls_back_to_reasoning_content(monkeypatch, tmp_path: Path) -> None:
    client = _client_with_fake_response(
        monkeypatch,
        tmp_path,
        {"content": "", "reasoning_content": '{"sql": "SELECT 3"}'},
    )

    assert client.chat_json("Return SQL", "question", retries=0) == {"sql": "SELECT 3"}


def test_chat_json_falls_back_to_raw_vllm_reasoning(monkeypatch, tmp_path: Path) -> None:
    client = _client_with_fake_response(
        monkeypatch,
        tmp_path,
        {"content": None, "reasoning": '{"sql": "SELECT 4"}'},
    )

    assert client.chat_json("Return SQL", "question", retries=0) == {"sql": "SELECT 4"}


def test_chat_json_still_fails_on_garbage(monkeypatch, tmp_path: Path) -> None:
    from sqlagent.llm import LLMUnavailable

    client = _client_with_fake_response(monkeypatch, tmp_path, {"content": "no json here at all"})

    try:
        client.chat_json("Return SQL", "question", retries=0)
    except LLMUnavailable as exc:
        assert "did not return JSON" in str(exc)
    else:
        raise AssertionError("garbage content must still raise LLMUnavailable")


def _build_kwargs(settings: Settings, tmp_path: Path) -> dict[str, object]:
    return {
        "provider": settings.llm_provider,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
        "opencode_go_base_url": settings.opencode_go_base_url,
        "opencode_go_api_key": settings.opencode_go_api_key,
        "opencode_go_model": settings.opencode_go_model,
        "litellm_base_url": settings.litellm_base_url,
        "litellm_api_key": settings.litellm_api_key,
        "litellm_model": settings.litellm_model,
        "cache_dir": tmp_path,
    }


def test_build_llm_selects_litellm(tmp_path: Path) -> None:
    from sqlagent.llm import LiteLLMClient

    settings = Settings(
        llm_provider="litellm",
        litellm_base_url="http://litellm:4000/v1",
        litellm_api_key="sk-test",
        litellm_model="hosted_vllm/gemma4-chat",
    )

    client = build_llm(**_build_kwargs(settings, tmp_path))

    assert isinstance(client, LiteLLMClient)
    assert client.model == "hosted_vllm/gemma4-chat"
    assert client.base_url == "http://litellm:4000/v1"


def test_build_llm_rejects_disabled_ollama(tmp_path: Path) -> None:
    settings = Settings(llm_provider="ollama")

    try:
        build_llm(**_build_kwargs(settings, tmp_path))
    except ValueError as exc:
        assert "temporarily disabled" in str(exc)
    else:
        raise AssertionError("ollama provider must be rejected while disabled")


def test_litellm_without_key_fails_before_network(tmp_path: Path) -> None:
    from sqlagent.llm import LiteLLMClient

    client = LiteLLMClient("http://litellm:4000/v1", "", "hosted_vllm/gemma4-chat", tmp_path)

    try:
        client.chat_text("system", "user")
    except Exception as exc:
        assert "LITELLM_API_KEY" in str(exc)
    else:
        raise AssertionError("missing LiteLLM key must fail explicitly")
