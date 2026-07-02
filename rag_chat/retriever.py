from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from common.config import Settings, load_settings
from common.embedding import EmbeddingTool, tokenize
from common.file_ops import read_json


@dataclass
class SearchResult:
    doc_id: str
    path: str
    title: str
    score: float
    snippet: str
    chunk_id: str = ""
    heading: str = ""


@dataclass
class HybridRetriever:
    settings: Settings | None = None
    embedding_tool: EmbeddingTool | None = None
    rrf_k: int = 60
    oversampling: int = 6

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.embedding_tool = self.embedding_tool or EmbeddingTool.from_settings(self.settings)
        self.fulltext_path = Path(self.settings.index_dir) / "fulltext_index.json"
        self.vector_path = Path(self.settings.index_dir) / "vector_index.json"

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        fulltext = dict(read_json(self.fulltext_path, default={"documents": {}, "chunks": {}, "terms": {}}))
        vectors = dict(read_json(self.vector_path, default={"documents": {}, "chunks": {}}))
        chunks = fulltext.get("chunks") or fulltext.get("documents", {})
        vector_chunks = vectors.get("chunks") or vectors.get("documents", {})
        candidate_k = max(top_k * self.oversampling, top_k)
        keyword_rank = self._keyword_rank(query, fulltext, chunks, candidate_k)
        vector_rank = self._vector_rank(query, vector_chunks, candidate_k)

        scores: dict[str, float] = {}
        for rank_map in (keyword_rank, vector_rank):
            for chunk_id, rank in rank_map.items():
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (self.rrf_k + rank)

        results: list[SearchResult] = []
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]:
            if score <= 0:
                continue
            info = vector_chunks.get(chunk_id) or chunks.get(chunk_id, {})
            content = info.get("content") or info.get("content_preview", "")
            query_tokens = tokenize(query)
            results.append(
                SearchResult(
                    doc_id=info.get("doc_id", chunk_id),
                    chunk_id=info.get("chunk_id", chunk_id),
                    path=info.get("path", ""),
                    title=info.get("title", chunk_id),
                    heading=info.get("heading", ""),
                    score=round(score, 6),
                    snippet=self._snippet(content, query_tokens),
                )
            )
        return results

    def _keyword_rank(self, query: str, fulltext: dict, chunks: dict, candidate_k: int) -> dict[str, int]:
        query_tokens = tokenize(query)
        raw_keyword: dict[str, float] = {}
        for token in query_tokens:
            postings = fulltext.get("terms", {}).get(token, {})
            idf = math.log((1 + len(chunks)) / (1 + len(postings))) + 1
            for chunk_id, count in postings.items():
                raw_keyword[chunk_id] = raw_keyword.get(chunk_id, 0.0) + float(count) * idf
        ordered = sorted(raw_keyword.items(), key=lambda item: item[1], reverse=True)[:candidate_k]
        return {chunk_id: rank for rank, (chunk_id, _) in enumerate(ordered, start=1)}

    def _vector_rank(self, query: str, vector_chunks: dict, candidate_k: int) -> dict[str, int]:
        query_embedding = self.embedding_tool.embed(query)
        raw_vector = []
        for chunk_id, info in vector_chunks.items():
            score = max(0.0, self.embedding_tool.cosine(query_embedding, info.get("embedding", [])))
            if score > 0:
                raw_vector.append((chunk_id, score))
        ordered = sorted(raw_vector, key=lambda item: item[1], reverse=True)[:candidate_k]
        return {chunk_id: rank for rank, (chunk_id, _) in enumerate(ordered, start=1)}

    @staticmethod
    def _snippet(content: str, tokens: list[str]) -> str:
        lower = content.lower()
        positions = [lower.find(token.lower()) for token in tokens if lower.find(token.lower()) >= 0]
        start = max(0, min(positions) - 80) if positions else 0
        return content[start : start + 300].replace("\n", " ")
