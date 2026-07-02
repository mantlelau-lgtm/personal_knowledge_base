from pathlib import Path
from types import SimpleNamespace

import pytest

from common.checkpoint import Checkpoint
from common.embedding import EmbeddingTool
from common.llm_client import LLMClient
from common.llm_gateway import LLMGateway
from common.prompt_registry import PromptRegistry
from common.file_ops import file_sha256, unique_path


def test_unique_path_and_hash(tmp_path):
    first = unique_path(tmp_path, "a.txt")
    first.write_text("hello", encoding="utf-8")
    second = unique_path(tmp_path, "a.txt")
    assert second.name == "a_1.txt"
    assert file_sha256(first) == file_sha256(first)


def test_checkpoint(settings):
    checkpoint = Checkpoint("unit", settings)
    checkpoint.mark_done("key", {"value": 1})
    checkpoint2 = Checkpoint("unit", settings)
    assert checkpoint2.is_done("key")
    assert checkpoint2.get("key")["value"] == 1


def test_embedding_similarity():
    tool = EmbeddingTool(dimension=16)
    same = tool.cosine(tool.embed("Python RAG"), tool.embed("Python RAG"))
    other = tool.cosine(tool.embed("Python RAG"), tool.embed("cooking"))
    assert same > other


def test_embedding_from_settings(settings):
    settings.embedding_provider = "local"
    settings.embedding_model = "hashing-local"
    settings.embedding_dimension = 32
    settings.embedding_api_key = ""
    settings.embedding_base_url = "https://example.com/v1"
    settings.embedding_timeout = 10
    tool = EmbeddingTool.from_settings(settings)
    assert tool.provider == "local"
    assert tool.model == "hashing-local"
    assert tool.base_url == "https://example.com/v1"
    assert len(tool.embed("Python")) == 32


def test_remote_embedding_requires_api_key():
    tool = EmbeddingTool(provider="openai-compatible", model="embed-model", api_key="")
    with pytest.raises(ValueError):
        tool.embed("Python")


def test_remote_embedding_uses_openai_compatible_client(monkeypatch, settings):
    calls = {}

    class FakeEmbeddings:
        def create(self, model, input):
            calls["model"] = model
            calls["input"] = input
            return SimpleNamespace(data=[SimpleNamespace(embedding=[3.0, 4.0])])

    class FakeOpenAI:
        def __init__(self, api_key, base_url, timeout):
            calls["api_key"] = api_key
            calls["base_url"] = base_url
            calls["timeout"] = timeout
            self.embeddings = FakeEmbeddings()

    fake_module = SimpleNamespace(OpenAI=FakeOpenAI)
    monkeypatch.setitem(__import__("sys").modules, "openai", fake_module)

    tool = EmbeddingTool(
        provider="openai-compatible",
        model="remote-embedding",
        api_key="key",
        base_url="https://example.com/v1/",
        timeout=5,
        gateway=LLMGateway(settings),
    )
    vector = tool.embed("Python")
    assert calls == {
        "api_key": "key",
        "base_url": "https://example.com/v1",
        "timeout": 5,
        "model": "remote-embedding",
        "input": "Python",
    }
    assert vector == [0.6, 0.8]


def test_llm_from_settings(settings):
    settings.llm_provider = "openai-compatible"
    settings.llm_model = "chat-model"
    settings.llm_api_key = "key"
    settings.llm_base_url = "https://example.com/v1"
    settings.llm_timeout = 7
    client = LLMClient.from_settings(settings)
    assert client.provider == "openai-compatible"
    assert client.model == "chat-model"
    assert client.api_key == "key"
    assert client.base_url == "https://example.com/v1"
    assert client.timeout == 7


def test_remote_llm_uses_openai_compatible_client(monkeypatch, settings):
    calls = {}

    class FakeCompletions:
        def create(self, model, messages):
            calls["model"] = model
            calls["messages"] = messages
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="远程回答"))])

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key, base_url, timeout):
            calls["api_key"] = api_key
            calls["base_url"] = base_url
            calls["timeout"] = timeout
            self.chat = FakeChat()

    monkeypatch.setitem(__import__("sys").modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    settings.llm_cache_enabled = False
    client = LLMClient(
        provider="openai-compatible",
        model="remote-chat",
        api_key="key",
        base_url="https://example.com/v1/",
        timeout=9,
        settings=settings,
    )
    assert client.complete("问题", "上下文") == "远程回答"
    assert calls["api_key"] == "key"
    assert calls["base_url"] == "https://example.com/v1"
    assert calls["timeout"] == 9
    assert calls["model"] == "remote-chat"


def test_llm_gateway_records_call(settings):
    gateway = LLMGateway(settings)
    result = gateway.record_call("local", "deterministic-local", "summarize", lambda: "回答内容", prompt_tokens=10)
    assert result == "回答内容"
    calls = gateway.recent_calls(5)
    assert calls
    assert calls[0]["purpose"] == "summarize"
    assert calls[0]["status"] == "ok"
    assert calls[0]["completion_tokens"] >= 1


def test_llm_gateway_records_error(settings):
    gateway = LLMGateway(settings)

    def boom():
        raise RuntimeError("失败")

    with pytest.raises(RuntimeError):
        gateway.record_call("local", "deterministic-local", "extract", boom, prompt_tokens=5)
    calls = gateway.recent_calls(5)
    assert calls[0]["status"] == "error"
    assert "失败" in calls[0]["error"]


def test_prompt_registry_loads_template(settings):
    prompt_dir = Path(settings.root_dir) / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "chat_system_v1.md").write_text("你是个人知识库 RAG 助手。", encoding="utf-8")
    (prompt_dir / "chat_user_v1.md").write_text("上下文：{{context}}\n问题：{{prompt}}", encoding="utf-8")
    registry = PromptRegistry(settings)
    text = registry.render("chat_system")
    assert "知识库" in text
    rendered = registry.render("chat_user", context="CTX", prompt="Q")
    assert "CTX" in rendered
    assert "Q" in rendered
