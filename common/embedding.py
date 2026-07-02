from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from common.llm_gateway import LLMGateway


_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if any("\u4e00" <= ch <= "\u9fff" for ch in token) and len(token) > 1:
            expanded.extend(list(token))
    return expanded


@dataclass
class EmbeddingTool:
    provider: str = "local"
    model: str = "hashing-local"
    dimension: int = 64
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    timeout: int = 30
    gateway: LLMGateway | None = None

    def __post_init__(self) -> None:
        self.gateway = self.gateway or LLMGateway()

    @classmethod
    def from_settings(cls, settings) -> "EmbeddingTool":
        return cls(
            provider=getattr(settings, "embedding_provider", "local"),
            model=getattr(settings, "embedding_model", "hashing-local"),
            dimension=getattr(settings, "embedding_dimension", 64),
            api_key=getattr(settings, "embedding_api_key", ""),
            base_url=getattr(settings, "embedding_base_url", "https://api.openai.com/v1"),
            timeout=getattr(settings, "embedding_timeout", 30),
        )

    @property
    def signature(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimension}:{self.base_url.rstrip('/')}"

    def embed(self, text: str) -> list[float]:
        if self.provider.lower() in {"openai", "openai-compatible", "remote"}:
            return self._remote_embed(text)
        return self._local_embed(text)

    def _local_embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token, count in Counter(tokenize(text)).items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign * float(count)
        return self._normalize(vector)

    def _remote_embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise ValueError("远程 embedding 需要配置 PKB_EMBEDDING_API_KEY 或 OPENAI_API_KEY")
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError("远程 embedding 需要安装 openai 依赖") from exc
        client = OpenAI(api_key=self.api_key, base_url=self.base_url.rstrip("/"), timeout=self.timeout)
        def call() -> list[float]:
            response = client.embeddings.create(model=self.model, input=text)
            vector = list(response.data[0].embedding)
            return self._normalize([float(value) for value in vector])
        return self.gateway.record_call(self.provider, self.model, "embedding", call, len(text) // 4)

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in vector))
        if norm:
            return [v / norm for v in vector]
        return vector

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        return sum(x * y for x, y in zip(a, b))
