from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from common.config import Settings, load_settings
from common.llm_client import LLMClient

from .retriever import HybridRetriever, SearchResult


@dataclass
class IterativeSearch:
    settings: Settings | None = None
    retriever: HybridRetriever | None = None
    llm_client: LLMClient | None = None
    max_rounds: int = 3

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.retriever = self.retriever or HybridRetriever(self.settings)
        self.llm_client = self.llm_client or LLMClient.from_settings(self.settings)

    def search(self, query: str, top_k: int = 5) -> tuple[list[SearchResult], list[dict[str, Any]]]:
        trace: list[dict[str, Any]] = []
        accumulated: list[SearchResult] = []
        seen_chunk_ids: set[str] = set()
        current_query = query

        for round_index in range(1, self.max_rounds + 1):
            round_results = self.retriever.search(current_query, top_k=top_k)
            top_score = round_results[0].score if round_results else 0.0
            trace.append(
                {
                    "round": round_index,
                    "query": current_query,
                    "hits": len(round_results),
                    "top_score": top_score,
                }
            )
            for result in round_results:
                key = result.chunk_id or result.doc_id
                if key in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(key)
                accumulated.append(result)

            if round_index >= self.max_rounds:
                break
            if not self._needs_more(round_results):
                break
            current_query = self._next_query(query, round_results)
            if not current_query:
                break

        accumulated.sort(key=lambda r: r.score, reverse=True)
        return accumulated, trace

    @staticmethod
    def _needs_more(results: list[SearchResult]) -> bool:
        if len(results) < 2:
            return True
        return results[0].score < 0.02

    def _next_query(self, query: str, results: list[SearchResult]) -> str:
        top_heading = results[0].heading if results else ""
        if self.llm_client and getattr(self.llm_client, "_is_remote", False):
            try:
                prompt = (
                    "已有查询：" + query + "\n"
                    "首个命中标题：" + top_heading + "\n"
                    "请给出一个更聚焦的补充查询，直接返回一行文本。"
                )
                supplement = self.llm_client.complete(prompt).strip()
                if supplement:
                    return supplement
            except Exception:
                pass
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", query)
        prefix = " ".join(tokens[:3])
        supplement = f"{prefix} {top_heading}".strip()
        if not supplement or supplement == query:
            return ""
        return supplement
