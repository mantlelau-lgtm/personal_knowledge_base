from __future__ import annotations

from dataclasses import dataclass

from common.llm_client import LLMClient

from .extract_schema import merge_extracted_knowledge, normalize_extracted_knowledge


@dataclass
class KnowledgeExtractor:
    llm_client: LLMClient

    def extract_chunk(self, text: str) -> dict:
        return normalize_extracted_knowledge(self.llm_client.extract_knowledge(text))

    def merge_chunks(self, chunks: list[dict]) -> dict:
        return merge_extracted_knowledge(chunks)
