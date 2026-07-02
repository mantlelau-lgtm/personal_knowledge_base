from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.embedding import EmbeddingTool, tokenize
from common.file_ops import file_sha256, read_json, read_text, write_json
from common.logging_config import setup_logger

from .chunking import split_markdown_chunks


@dataclass
class Indexer:
    settings: Settings | None = None
    embedding_tool: EmbeddingTool | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.embedding_tool = self.embedding_tool or EmbeddingTool.from_settings(self.settings)
        self.logger = setup_logger("indexer", self.settings)
        self.fulltext_path = Path(self.settings.index_dir) / "fulltext_index.json"
        self.vector_path = Path(self.settings.index_dir) / "vector_index.json"
        self.manifest_path = Path(self.settings.index_dir) / "manifest.json"

    def _wiki_files(self) -> list[Path]:
        return sorted(Path(self.settings.wiki_dir).glob("**/*.md"))

    def update_indexes(self) -> dict[str, int]:
        manifest = {str(k): v for k, v in dict(read_json(self.manifest_path, default={})).items()}
        fulltext: dict[str, Any] = dict(read_json(self.fulltext_path, default={"terms": {}, "documents": {}}))
        vectors: dict[str, Any] = dict(read_json(self.vector_path, default={"documents": {}}))
        fulltext.setdefault("terms", {})
        fulltext.setdefault("documents", {})
        fulltext.setdefault("chunks", {})
        vectors.setdefault("documents", {})
        vectors.setdefault("chunks", {})

        current_paths = {str(path) for path in self._wiki_files()}
        removed = set(manifest) - current_paths
        for removed_path in removed:
            doc_id = manifest[removed_path].get("doc_id", removed_path)
            fulltext["documents"].pop(doc_id, None)
            vectors["documents"].pop(doc_id, None)
            for chunk_id in list(fulltext.get("chunks", {})):
                if chunk_id.startswith(f"{doc_id}#"):
                    fulltext["chunks"].pop(chunk_id, None)
                    vectors.get("chunks", {}).pop(chunk_id, None)
            manifest.pop(removed_path, None)

        updated = 0
        for path in self._wiki_files():
            path_str = str(path)
            digest = file_sha256(path)
            previous = manifest.get(path_str, {})
            if previous.get("hash") == digest and previous.get("embedding_signature") == self.embedding_tool.signature:
                continue
            text = read_text(path)
            doc_id = path.relative_to(self.settings.wiki_dir).as_posix()
            chunk_infos = split_markdown_chunks(text)
            doc_token_counts = Counter(tokenize(text))
            fulltext["documents"][doc_id] = {
                "path": path_str,
                "title": path.stem,
                "token_counts": dict(doc_token_counts),
                "length": sum(doc_token_counts.values()),
                "content_preview": text[:500],
            }
            for old_chunk_id in list(fulltext.get("chunks", {})):
                if old_chunk_id.startswith(f"{doc_id}#"):
                    fulltext["chunks"].pop(old_chunk_id, None)
                    vectors.get("chunks", {}).pop(old_chunk_id, None)
            fulltext.setdefault("chunks", {})
            vectors.setdefault("chunks", {})
            for index, chunk in enumerate(chunk_infos, start=1):
                chunk_id = f"{doc_id}#chunk-{index:03d}"
                chunk_text = chunk["text"]
                token_counts = Counter(tokenize(chunk_text))
                fulltext["chunks"][chunk_id] = {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "path": path_str,
                    "title": path.stem,
                    "heading": chunk["heading"],
                    "token_counts": dict(token_counts),
                    "length": sum(token_counts.values()),
                    "content_preview": chunk_text[:500],
                }
                vectors["chunks"][chunk_id] = {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "path": path_str,
                    "title": path.stem,
                    "heading": chunk["heading"],
                    "embedding": self.embedding_tool.embed(chunk_text),
                    "content": chunk_text,
                }
            vectors["documents"][doc_id] = {
                "path": path_str,
                "title": path.stem,
                "embedding": self.embedding_tool.embed(text),
                "content": text,
            }
            manifest[path_str] = {
                "hash": digest,
                "doc_id": doc_id,
                "embedding_signature": self.embedding_tool.signature,
            }
            updated += 1

        terms: dict[str, dict[str, int]] = defaultdict(dict)
        for chunk_id, info in fulltext.get("chunks", {}).items():
            for token, count in info.get("token_counts", {}).items():
                terms[token][chunk_id] = count
        fulltext["terms"] = dict(terms)
        write_json(self.fulltext_path, fulltext)
        write_json(self.vector_path, vectors)
        write_json(self.manifest_path, manifest)
        self.logger.info("updated indexes: %s documents changed", updated)
        return {"documents": len(current_paths), "chunks": len(fulltext.get("chunks", {})), "updated": updated}
