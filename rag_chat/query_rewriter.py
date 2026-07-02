from __future__ import annotations

import json
import re
from dataclasses import dataclass

from common.config import Settings, load_settings
from common.llm_client import LLMClient
from common.prompt_registry import PromptRegistry


@dataclass
class QueryRewriter:
    settings: Settings | None = None
    llm_client: LLMClient | None = None
    prompts: PromptRegistry | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.llm_client = self.llm_client or LLMClient.from_settings(self.settings)
        self.prompts = self.prompts or PromptRegistry(self.settings)

    def rewrite(self, query: str, history: list[dict[str, str]] | None = None) -> str:
        query = query.strip()
        if not query:
            return query
        recent = [m for m in (history or [])[-4:] if m.get("role") == "user" and m.get("content")]
        if not recent:
            return query
        if len(query) >= 12 and self._looks_self_contained(query):
            return query
        if not self.llm_client._is_remote:
            return self._local_rewrite(query, recent)
        return self._remote_rewrite(query, recent)

    def _looks_self_contained(self, query: str) -> bool:
        if any(p in query for p in ("它", "他", "她", "这个", "那个", "上面", "刚才", "它", "其")):
            return False
        return True

    def _local_rewrite(self, query: str, recent: list[dict[str, str]]) -> str:
        previous = recent[-1]["content"][:60]
        return f"{previous} {query}".strip()

    def _remote_rewrite(self, query: str, recent: list[dict[str, str]]) -> str:
        history_text = "\n".join(f"用户：{m['content']}" for m in recent)
        template = self.prompts.render("query_rewrite", history=history_text, query=query)
        if not template:
            template = (
                "根据对话历史，把用户最新问题改写为一个独立、完整的检索查询。"
                "只输出改写后的查询，不要解释。\n\n"
                f"对话历史：\n{history_text}\n\n最新问题：{query}\n\n改写后的查询："
            )
        content = self.llm_client._chat_completion(template)
        rewritten = content.strip().strip('"').splitlines()[0].strip() if content.strip() else ""
        return rewritten or self._local_rewrite(query, recent)
