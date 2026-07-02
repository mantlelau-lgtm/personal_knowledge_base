from __future__ import annotations

from pathlib import Path

from common.prompt_registry import PromptRegistry
from common.prompt_router import PromptRouter


def _prep_prompts(settings) -> Path:
    prompt_dir = Path(settings.root_dir) / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "chat_system_v1.md").write_text("你是助手 v1", encoding="utf-8")
    (prompt_dir / "chat_system_v2.md").write_text("你是助手 v2", encoding="utf-8")
    (prompt_dir / "chat_user_v1.md").write_text("上下文：{{context}}\n问题：{{prompt}}", encoding="utf-8")
    return prompt_dir


def test_prompt_registry_list_prompts(settings):
    _prep_prompts(settings)
    registry = PromptRegistry(settings)
    prompts = registry.list_prompts()
    names = {p["name"]: p["versions"] for p in prompts}
    assert "chat_system" in names
    assert set(names["chat_system"]) == {"v1", "v2"}
    assert names["chat_user"] == ["v1"]
    assert registry.available_versions("chat_system") == ["v1", "v2"]


def test_prompt_router_register_and_list(settings):
    _prep_prompts(settings)
    router = PromptRouter(settings)
    result = router.register("chat_system", "v1")
    assert result["name"] == "chat_system"
    assert result["content"].startswith("你是助手")
    listing = router.list("chat_system")
    assert len(listing) == 1
    assert str(listing[0]["version"]) == "v1"


def test_prompt_router_set_traffic(settings):
    _prep_prompts(settings)
    router = PromptRouter(settings)
    router.register("chat_system", "v1", traffic_percent=100)
    router.register("chat_system", "v2", traffic_percent=0)
    router.set_traffic("chat_system", {"v1": 30, "v2": 70})
    rows = {str(r["version"]): int(r["traffic_percent"]) for r in router.list("chat_system")}
    assert rows["v1"] == 30
    assert rows["v2"] == 70


def test_prompt_router_pick_only_v1(settings):
    _prep_prompts(settings)
    router = PromptRouter(settings)
    router.register("chat_system", "v1", traffic_percent=100)
    for _ in range(20):
        assert router.pick("chat_system") == "v1"


def test_prompt_router_pick_empty_fallback(settings):
    _prep_prompts(settings)
    router = PromptRouter(settings)
    assert router.pick("nonexistent") == "v1"


def test_prompt_router_render(settings):
    _prep_prompts(settings)
    router = PromptRouter(settings)
    router.register("chat_user", "v1", traffic_percent=100)
    version, text = router.render("chat_user", context="CTX", prompt="Q")
    assert version == "v1"
    assert "CTX" in text and "Q" in text


def test_prompt_router_render_missing_returns_empty(settings):
    (Path(settings.root_dir) / "prompts").mkdir(parents=True, exist_ok=True)
    router = PromptRouter(settings)
    version, text = router.render("does_not_exist")
    assert version == "v1"
    assert text == ""
