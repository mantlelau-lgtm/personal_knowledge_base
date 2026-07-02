from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.file_ops import write_json

from .models import GraphEdge, GraphNode, KnowledgeGraph


@dataclass
class GraphStore:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.path = Path(self.settings.index_dir) / "graph.json"  # type: ignore[arg-type]

    def update(self, graph: KnowledgeGraph) -> None:
        data: dict[str, Any] = graph.to_dict()
        data["updated_at"] = datetime.now().isoformat()
        write_json(self.path, data)

    def load(self) -> KnowledgeGraph | None:
        if not self.path.exists():
            return None
        import json

        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        nodes = [
            GraphNode(
                id=str(n.get("id", n.get("name", ""))),
                name=str(n.get("name", "")),
                type=str(n.get("type", "")),
                doc_id=str(n.get("doc_id", "")),
                weight=int(n.get("weight", 1)),
            )
            for n in (data.get("nodes") or [])
            if isinstance(n, dict)
        ]
        edges = [
            GraphEdge(
                source=str(e.get("source", "")),
                target=str(e.get("target", "")),
                relation=str(e.get("relation", "")),
                doc_id=str(e.get("doc_id", "")),
            )
            for e in (data.get("edges") or [])
            if isinstance(e, dict)
        ]
        return KnowledgeGraph(nodes=nodes, edges=edges)
