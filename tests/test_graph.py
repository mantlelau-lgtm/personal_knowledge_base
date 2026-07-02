from __future__ import annotations

import json
from pathlib import Path

from graph.builder import GraphBuilder, build_graph
from graph.models import GraphNode, KnowledgeGraph
from graph.query import GraphQuery
from graph.store import GraphStore


SAMPLE_TEXT = """---
knowledge: {"entities":[{"name":"Python","type":"language"},{"name":"RAG","type":"concept"}],"concepts":[{"name":"Embedding","description":"vector"}],"connections":[{"source":"Python","target":"RAG","relation":"enables"},{"source":"RAG","target":"Embedding","relation":"uses"}]}
---

# Test Doc
"""

CHAIN_TEXT = """---
knowledge: {"entities":[{"name":"A","type":"node"},{"name":"B","type":"node"},{"name":"C","type":"node"},{"name":"D","type":"node"}],"connections":[{"source":"A","target":"B","relation":"r"},{"source":"B","target":"C","relation":"r"},{"source":"C","target":"D","relation":"r"},{"source":"A","target":"C","relation":"r"}]}
---

# Chain
"""


def test_build_from_text_basic():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    names = graph.node_names()
    assert "Python" in names
    assert "RAG" in names
    assert "Embedding" in names
    assert len(graph.edges) == 2
    python_edges = graph.neighbors("Python")
    assert any(e.target == "RAG" and e.relation == "enables" for e in python_edges)


def test_build_from_text_node_type_from_entity():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    python_node = next(n for n in graph.nodes if n.name == "Python")
    assert python_node.type == "language"
    rag_node = next(n for n in graph.nodes if n.name == "RAG")
    assert rag_node.type == "concept"


def test_build_from_text_weight_accumulation():
    text = """---
knowledge: {"entities":[{"name":"Python","type":"language"}],"concepts":[{"name":"Python","description":"a lang"}]}
---

# Doc
"""
    builder = GraphBuilder()
    graph = builder.build_from_text(text, "doc1")
    python_node = next(n for n in graph.nodes if n.name == "Python")
    assert python_node.weight == 2
    assert python_node.type == "language"


def test_build_from_text_edge_dedup():
    text = """---
knowledge: {"entities":[{"name":"A","type":"x"},{"name":"B","type":"x"}],"connections":[{"source":"A","target":"B","relation":"r"},{"source":"A","target":"B","relation":"r"}]}
---

# Doc
"""
    builder = GraphBuilder()
    graph = builder.build_from_text(text, "doc1")
    assert len(graph.edges) == 1


def test_build_from_text_empty():
    builder = GraphBuilder()
    graph = builder.build_from_text("no front matter here", "doc1")
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


def test_query_find():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    query = GraphQuery(graph)
    node = query.find("Python")
    assert node is not None
    assert node.name == "Python"
    assert query.find("NotExist") is None


def test_query_neighbors_depth1():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    query = GraphQuery(graph)
    nbrs = query.neighbors("Python", depth=1)
    names = {n.name for n in nbrs}
    assert names == {"RAG"}


def test_query_neighbors_depth2():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    query = GraphQuery(graph)
    nbrs = query.neighbors("Python", depth=2)
    names = {n.name for n in nbrs}
    assert "RAG" in names
    assert "Embedding" in names


def test_query_neighbors_bidirectional():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    query = GraphQuery(graph)
    nbrs = query.neighbors("Embedding", depth=1)
    assert {n.name for n in nbrs} == {"RAG"}


def test_query_path_shortest():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    p = query.path("A", "D")
    assert p == ["A", "C", "D"]


def test_query_path_direct():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    p = query.path("A", "C")
    assert p == ["A", "C"]


def test_query_path_not_found():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    assert query.path("A", "NotExist") == []


def test_query_path_same_node():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    assert query.path("A", "A") == ["A"]


def test_query_path_max_depth():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    p = query.path("A", "D", max_depth=1)
    assert p == []


def test_subgraph_includes_neighbors():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    sub = query.subgraph(["A"])
    names = sub.node_names()
    assert "A" in names
    assert "B" in names
    assert "C" in names
    assert "D" not in names


def test_subgraph_edges_filtered():
    builder = GraphBuilder()
    graph = builder.build_from_text(CHAIN_TEXT, "doc1")
    query = GraphQuery(graph)
    sub = query.subgraph(["A"])
    for edge in sub.edges:
        assert edge.source in sub.node_names()
        assert edge.target in sub.node_names()


def test_to_dict_roundtrip():
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    d = graph.to_dict()
    assert "nodes" in d
    assert "edges" in d
    assert len(d["nodes"]) == 3
    assert len(d["edges"]) == 2


def test_store_update_and_load(settings):
    store = GraphStore(settings)
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    store.update(graph)
    assert store.path.exists()
    loaded = store.load()
    assert loaded is not None
    assert "Python" in loaded.node_names()
    assert "RAG" in loaded.node_names()
    assert any(e.source == "Python" and e.target == "RAG" for e in loaded.edges)


def test_store_updated_at(settings):
    store = GraphStore(settings)
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    store.update(graph)
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert "updated_at" in data
    assert "nodes" in data
    assert "edges" in data


def test_store_load_missing_file(settings):
    store = GraphStore(settings)
    assert store.load() is None


def test_store_load_preserves_weight(settings):
    store = GraphStore(settings)
    builder = GraphBuilder()
    graph = builder.build_from_text(SAMPLE_TEXT, "doc1")
    graph.nodes[0].weight = 5
    store.update(graph)
    loaded = store.load()
    assert loaded is not None
    python_node = next(n for n in loaded.nodes if n.name == "Python")
    assert python_node.weight == 5


def test_build_graph_scans_wiki(settings):
    wiki_dir = Path(settings.wiki_dir)
    (wiki_dir / "doc1.md").write_text(SAMPLE_TEXT, encoding="utf-8")
    graph = build_graph(settings)
    assert "Python" in graph.node_names()
    assert "RAG" in graph.node_names()
    assert any(e.source == "Python" and e.target == "RAG" for e in graph.edges)


def test_build_graph_merges_multiple_docs(settings):
    wiki_dir = Path(settings.wiki_dir)
    doc1 = """---
knowledge: {"entities":[{"name":"Python","type":"language"}],"connections":[]}
---

# Doc1
"""
    doc2 = """---
knowledge: {"entities":[{"name":"Python","type":"lang"},{"name":"Flask","type":"framework"}],"connections":[{"source":"Python","target":"Flask","relation":"has"}]}
---

# Doc2
"""
    (wiki_dir / "doc1.md").write_text(doc1, encoding="utf-8")
    (wiki_dir / "doc2.md").write_text(doc2, encoding="utf-8")
    graph = build_graph(settings)
    python_node = next(n for n in graph.nodes if n.name == "Python")
    assert python_node.weight == 2
    assert python_node.type == "language"
    assert "Flask" in graph.node_names()
    assert any(e.source == "Python" and e.target == "Flask" for e in graph.edges)
