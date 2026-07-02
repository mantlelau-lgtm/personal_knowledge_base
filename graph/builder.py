from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.file_ops import read_text
from data_parsing.processor import parse_front_matter

from .models import GraphEdge, GraphNode, KnowledgeGraph


@dataclass
class GraphBuilder:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()

    def build(self) -> KnowledgeGraph:
        wiki_dir = Path(self.settings.wiki_dir)  # type: ignore[arg-type]
        graph = KnowledgeGraph()
        for path in sorted(wiki_dir.rglob("*.md")):
            text = read_text(path)
            sub = self.build_from_text(text, path.stem)
            self._merge(graph, sub)
        return graph

    def build_from_text(self, text: str, doc_id: str) -> KnowledgeGraph:
        metadata, _ = parse_front_matter(text)
        knowledge: Any = metadata.get("knowledge") or {}
        if not isinstance(knowledge, dict):
            return KnowledgeGraph()
        nodes_map: dict[str, GraphNode] = {}
        for entity in knowledge.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            node_type = str(entity.get("type", "")).strip()
            self._add_node(nodes_map, name, node_type, doc_id)
        for concept in knowledge.get("concepts") or []:
            if not isinstance(concept, dict):
                continue
            name = str(concept.get("name", "")).strip()
            if not name:
                continue
            self._add_node(nodes_map, name, "", doc_id)
        graph = KnowledgeGraph()
        graph.nodes = list(nodes_map.values())
        seen_edges: set[tuple[str, str, str]] = set()
        for conn in knowledge.get("connections") or []:
            if not isinstance(conn, dict):
                continue
            source = str(conn.get("source", "")).strip()
            target = str(conn.get("target", "")).strip()
            relation = str(conn.get("relation", "")).strip()
            if not source or not target:
                continue
            key = (source, target, relation)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            graph.edges.append(GraphEdge(source=source, target=target, relation=relation, doc_id=doc_id))
        return graph

    @staticmethod
    def _add_node(nodes_map: dict[str, GraphNode], name: str, node_type: str, doc_id: str) -> None:
        if name in nodes_map:
            nodes_map[name].weight += 1
            if not nodes_map[name].type and node_type:
                nodes_map[name].type = node_type
        else:
            nodes_map[name] = GraphNode(id=name, name=name, type=node_type, doc_id=doc_id, weight=1)

    @staticmethod
    def _merge(target: KnowledgeGraph, source: KnowledgeGraph) -> None:
        nodes_map: dict[str, GraphNode] = {n.name: n for n in target.nodes}
        for node in source.nodes:
            if node.name in nodes_map:
                existing = nodes_map[node.name]
                existing.weight += node.weight
                if not existing.type and node.type:
                    existing.type = node.type
            else:
                target.nodes.append(node)
                nodes_map[node.name] = node
        seen_edges = {(e.source, e.target, e.relation) for e in target.edges}
        for edge in source.edges:
            key = (edge.source, edge.target, edge.relation)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            target.edges.append(edge)


def build_graph(settings: Settings | None = None) -> KnowledgeGraph:
    return GraphBuilder(settings).build()
