from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import GraphNode, KnowledgeGraph


@dataclass
class GraphQuery:
    graph: KnowledgeGraph

    def find(self, name: str) -> GraphNode | None:
        for node in self.graph.nodes:
            if node.name == name:
                return node
        return None

    def neighbors(self, name: str, depth: int = 1) -> list[GraphNode]:
        if depth < 1:
            return []
        node_map = {n.name: n for n in self.graph.nodes}
        visited: set[str] = {name}
        result: list[GraphNode] = []
        queue: deque[tuple[str, int]] = deque([(name, 0)])
        while queue:
            current, d = queue.popleft()
            if d >= depth:
                continue
            for edge in self.graph.edges:
                neighbor: str | None = None
                if edge.source == current:
                    neighbor = edge.target
                elif edge.target == current:
                    neighbor = edge.source
                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    if neighbor in node_map:
                        result.append(node_map[neighbor])
                    queue.append((neighbor, d + 1))
        return result

    def path(self, src: str, dst: str, max_depth: int = 4) -> list[str]:
        if src == dst:
            return [src] if self.find(src) else []
        visited: set[str] = {src}
        queue: deque[tuple[str, list[str]]] = deque([(src, [src])])
        while queue:
            current, trail = queue.popleft()
            if len(trail) - 1 >= max_depth:
                continue
            for edge in self.graph.edges:
                neighbor: str | None = None
                if edge.source == current:
                    neighbor = edge.target
                elif edge.target == current:
                    neighbor = edge.source
                if neighbor and neighbor not in visited:
                    new_trail = trail + [neighbor]
                    if neighbor == dst:
                        return new_trail
                    visited.add(neighbor)
                    queue.append((neighbor, new_trail))
        return []

    def subgraph(self, names: list[str]) -> KnowledgeGraph:
        node_map = {n.name: n for n in self.graph.nodes}
        included: set[str] = set()
        for name in names:
            if name in node_map:
                included.add(name)
            for edge in self.graph.edges:
                if edge.source == name and edge.target in node_map:
                    included.add(edge.target)
                elif edge.target == name and edge.source in node_map:
                    included.add(edge.source)
        nodes = [node_map[n] for n in included if n in node_map]
        edges = [
            e for e in self.graph.edges
            if e.source in included and e.target in included
        ]
        return KnowledgeGraph(nodes=nodes, edges=edges)
