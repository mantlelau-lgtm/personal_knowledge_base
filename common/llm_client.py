from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from common.config import Settings, load_settings
from common.llm_cache import LLMCache
from common.llm_gateway import LLMGateway
from common.llm_router import ModelRouter
from common.prompt_registry import PromptRegistry
from common.prompt_router import PromptRouter


@dataclass
class LLMClient:
    provider: str = "local"
    model: str = "deterministic-local"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    timeout: int = 60
    gateway: LLMGateway | None = None
    prompts: PromptRegistry | None = None
    prompt_router: PromptRouter | None = None
    settings: Settings | None = None
    router: ModelRouter | None = field(default=None)
    cache: LLMCache | None = field(default=None)

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        if self.model:
            self.settings.llm_model = self.model
        self.gateway = self.gateway or LLMGateway(settings=self.settings)
        self.prompts = self.prompts or PromptRegistry(settings=self.settings)
        self.prompt_router = self.prompt_router or PromptRouter(settings=self.prompts.settings, registry=self.prompts)
        self.router = self.router or ModelRouter(settings=self.settings)
        self._cache_enabled = bool(getattr(self.settings, "llm_cache_enabled", True))
        if self._cache_enabled:
            self.cache = self.cache or LLMCache(settings=self.settings)
        else:
            self.cache = None

    @classmethod
    def from_settings(cls, settings) -> "LLMClient":
        return cls(
            provider=getattr(settings, "llm_provider", "local"),
            model=getattr(settings, "llm_model", "deterministic-local"),
            api_key=getattr(settings, "llm_api_key", ""),
            base_url=getattr(settings, "llm_base_url", "https://api.openai.com/v1"),
            timeout=getattr(settings, "llm_timeout", 60),
            settings=settings,
        )

    def summarize(self, text: str) -> dict[str, object]:
        if self._is_remote:
            return self._remote_summarize(text)
        return self._local_summarize(text)

    def extract_knowledge(self, text: str) -> dict[str, object]:
        if self._is_remote:
            return self._remote_extract_knowledge(text)
        summary = self._local_summarize(text)
        return {
            "summary": summary["core_topic"],
            "concepts": [{"name": x, "description": ""} for x in summary.get("related_entities", [])[:8]],
            "entities": [{"name": x, "type": "concept"} for x in summary.get("related_entities", [])[:8]],
            "decisions": [],
            "action_items": [],
            "claims": [{"text": x, "evidence": ""} for x in summary.get("key_points", [])[:10]],
            "topics": [summary["core_topic"]],
            "connections": [],
        }

    def _local_summarize(self, text: str) -> dict[str, object]:
        words = re.findall(r"[\w\u4e00-\u9fff]+", text)
        title = " ".join(words[:8]) if words else "空文档"
        sentences = [s.strip() for s in re.split(r"[。！？.!?\n]+", text) if s.strip()]
        key_points = sentences[:5] or ([text[:120]] if text else [])
        entities = []
        for token in words:
            if len(token) >= 2 and token not in entities:
                entities.append(token)
            if len(entities) >= 8:
                break
        return {
            "core_topic": title[:80],
            "key_points": key_points,
            "related_entities": entities,
        }

    def complete(self, prompt: str, context: str = "") -> str:
        if self._is_remote:
            return self._remote_complete(prompt, context)
        if context:
            return f"基于本地知识库检索结果：{context[:500]}\n\n针对问题的回答：{prompt}"
        return f"未检索到足够上下文。问题：{prompt}"

    def stream_complete(self, prompt: str, context: str = ""):
        if self._is_remote:
            yield from self._remote_stream_complete(prompt, context)
            return
        answer = self.complete(prompt, context)
        for char in answer:
            yield char

    def _remote_stream_complete(self, prompt: str, context: str = ""):
        sys_version, system = self.prompt_router.render("chat_system")
        if not system:
            system = self.prompts.render("chat_system") or "你是个人知识库 RAG 助手。回答必须基于给定上下文；如上下文不足，请说明不足。"
            sys_version = "v1"
        usr_version, user = self.prompt_router.render("chat_user", context=context, prompt=prompt)
        if not user:
            user = self.prompts.render("chat_user", context=context, prompt=prompt) or f"上下文：\n{context}\n\n问题：\n{prompt}"
            usr_version = "v1"
        route_model = self.router.pick("default")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            stream = self._client().chat.completions.create(model=route_model, messages=messages, stream=True)
        except Exception:
            yield self._remote_complete(prompt, context)
            return
        collected: list[str] = []
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                token = getattr(delta, "content", None) or ""
            except Exception:
                token = ""
            if token:
                collected.append(token)
                yield token
        self.gateway.log_call(
            provider=self.provider,
            model=route_model,
            purpose=f"chat_stream:{usr_version}",
            prompt_tokens=(len(system) + len(user)) // 4,
            completion_tokens=max(1, len("".join(collected)) // 4),
            latency_ms=0,
            status="ok",
        )

    def summarize_json(self, text: str) -> str:
        return json.dumps(self.summarize(text), ensure_ascii=False)

    @property
    def _is_remote(self) -> bool:
        return self.provider.lower() in {"openai", "openai-compatible", "remote"}

    def _client(self):
        if not self.api_key:
            raise ValueError("远程 LLM 需要配置 PKB_LLM_API_KEY 或 OPENAI_API_KEY")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError("远程 LLM 需要安装 openai 依赖") from exc
        return OpenAI(api_key=self.api_key, base_url=self.base_url.rstrip("/"), timeout=self.timeout)

    def _remote_summarize(self, text: str) -> dict[str, object]:
        version, prompt = self.prompt_router.render("summarize", text=text[:6000])
        if not prompt:
            prompt = self.prompts.render("summarize", text=text[:6000]) or (
                "请把下面 Markdown 文档片段提炼为 JSON，必须只输出 JSON，不要 Markdown。"
                "字段：core_topic 字符串，key_points 字符串数组，related_entities 字符串数组。\n\n"
                f"文档片段：\n{text[:6000]}"
            )
            version = "v1"
        route_model = self.router.pick("summarize")
        purpose = f"summarize:{version}"
        cache_key = None
        if self._cache_enabled and self.cache is not None:
            cache_key = LLMCache.make_key("summarize", route_model, prompt, "")
            cached = self.cache.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        def call() -> dict[str, object]:
            content = self._chat_completion(prompt, model=route_model)
            try:
                data = json.loads(self._extract_json(content))
                return {
                    "core_topic": str(data.get("core_topic") or "未命名主题"),
                    "key_points": [str(x) for x in data.get("key_points", [])][:20],
                    "related_entities": [str(x) for x in data.get("related_entities", [])][:30],
                }
            except Exception:
                return self._local_summarize(text)

        result = self.gateway.record_call(self.provider, route_model, purpose, call, len(prompt) // 4)
        if self._cache_enabled and self.cache is not None and cache_key is not None:
            try:
                self.cache.set(cache_key, "summarize", route_model, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        return result

    def _remote_complete(self, prompt: str, context: str = "") -> str:
        sys_version, system = self.prompt_router.render("chat_system")
        if not system:
            system = self.prompts.render("chat_system") or "你是个人知识库 RAG 助手。回答必须基于给定上下文；如上下文不足，请说明不足。"
            sys_version = "v1"
        usr_version, user = self.prompt_router.render("chat_user", context=context, prompt=prompt)
        if not user:
            user = self.prompts.render("chat_user", context=context, prompt=prompt) or f"上下文：\n{context}\n\n问题：\n{prompt}"
            usr_version = "v1"
        route_model = self.router.pick("default")
        purpose = f"chat:{usr_version}"
        cache_key = None
        if self._cache_enabled and self.cache is not None:
            cache_key = LLMCache.make_key("chat", route_model, prompt, context)
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        result = self.gateway.record_call(
            self.provider,
            route_model,
            purpose,
            lambda: self._chat_completion(user, system=system, model=route_model),
            (len(system) + len(user)) // 4,
        )
        if self._cache_enabled and self.cache is not None and cache_key is not None:
            try:
                self.cache.set(cache_key, "chat", route_model, result)
            except Exception:
                pass
        return result

    def _remote_extract_knowledge(self, text: str) -> dict[str, object]:
        version, prompt = self.prompt_router.render("extract", text=text[:6000])
        if not prompt:
            prompt = self.prompts.render("extract", text=text[:6000]) or (
                "请从下面 Markdown 文档片段中抽取结构化知识，必须只输出 JSON，不要 Markdown。"
                "JSON 字段必须包含："
                "summary 字符串；"
                "concepts 数组，每项包含 name、description；"
                "entities 数组，每项包含 name、type；"
                "decisions 数组，每项包含 what、why、when；"
                "action_items 数组，每项包含 task、owner、due；"
                "claims 数组，每项包含 text、evidence；"
                "topics 字符串数组；"
                "connections 数组，每项包含 source、target、relation。\n\n"
                f"文档片段：\n{text[:6000]}"
            )
            version = "v1"
        route_model = self.router.pick("extract")
        purpose = f"extract:{version}"
        cache_key = None
        if self._cache_enabled and self.cache is not None:
            cache_key = LLMCache.make_key("extract", route_model, prompt, "")
            cached = self.cache.get(cache_key)
            if cached is not None:
                try:
                    return json.loads(cached)
                except Exception:
                    pass

        def call() -> dict[str, object]:
            content = self._chat_completion(prompt, model=route_model)
            try:
                data = json.loads(self._extract_json(content))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            return self.extract_knowledge(text) if not self._is_remote else self._local_extract_fallback(text)

        result = self.gateway.record_call(self.provider, route_model, purpose, call, len(prompt) // 4)
        if self._cache_enabled and self.cache is not None and cache_key is not None and isinstance(result, dict):
            try:
                self.cache.set(cache_key, "extract", route_model, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        return result

    def _local_extract_fallback(self, text: str) -> dict[str, object]:
        provider = self.provider
        self.provider = "local"
        try:
            return self.extract_knowledge(text)
        finally:
            self.provider = provider

    def _chat_completion(self, user: str, system: str | None = None, model: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        response = self._client().chat.completions.create(model=model or self.model, messages=messages)
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        self._last_prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        self._last_completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return content

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        return match.group(0) if match else text
