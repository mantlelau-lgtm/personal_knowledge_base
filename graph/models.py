from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GraphNode:
    id: str
    name: str
    type: str = ""
    doc_id: str = ""
    weight: int = 1


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str = ""
    doc_id: str = ""


@dataclass
class KnowledgeGraph:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type,
                    "doc_id": n.doc_id,
                    "weight": n.weight,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation,
                    "doc_id": e.doc_id,
                }
                for e in self.edges
            ],
        }

    def node_names(self) -> set[str]:
        return {n.name for n in self.nodes}

    def neighbors(self, name: str) -> list[GraphEdge]:
        return [e for e in self.edges if e.source == name or e.target == name]
