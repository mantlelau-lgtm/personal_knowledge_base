from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Concept:
    name: str
    description: str = ""


@dataclass
class Entity:
    name: str
    type: str = "concept"


@dataclass
class Decision:
    what: str
    why: str = ""
    when: str = ""


@dataclass
class ActionItem:
    task: str
    owner: str = ""
    due: str = ""


@dataclass
class Claim:
    text: str
    evidence: str = ""


@dataclass
class Connection:
    source: str
    target: str
    relation: str = "related_to"


@dataclass
class ExtractedKnowledge:
    summary: str = ""
    concepts: list[Concept] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_extracted_knowledge(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    knowledge = ExtractedKnowledge(
        summary=str(data.get("summary") or data.get("core_topic") or ""),
        concepts=[_concept(x) for x in data.get("concepts", [])][:30],
        entities=[_entity(x) for x in data.get("entities") or data.get("related_entities", [])][:50],
        decisions=[_decision(x) for x in data.get("decisions", [])][:30],
        action_items=[_action_item(x) for x in data.get("action_items", [])][:30],
        claims=[_claim(x) for x in data.get("claims") or data.get("key_points", [])][:50],
        topics=[str(x) for x in data.get("topics", []) if str(x).strip()][:30],
        connections=[_connection(x) for x in data.get("connections", [])][:50],
    )
    if not knowledge.topics and data.get("core_topic"):
        knowledge.topics = [str(data["core_topic"])]
    return knowledge.to_dict()


def merge_extracted_knowledge(items: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = normalize_extracted_knowledge({})
    summaries: list[str] = []
    seen: dict[str, set[str]] = {key: set() for key in merged if isinstance(merged[key], list)}
    for item in items:
        normalized = normalize_extracted_knowledge(item)
        if normalized.get("summary"):
            summaries.append(str(normalized["summary"]))
        for key, value in normalized.items():
            if key == "summary" or not isinstance(value, list):
                continue
            for entry in value:
                marker = _marker(entry)
                if marker not in seen[key]:
                    merged[key].append(entry)
                    seen[key].add(marker)
    merged["summary"] = summaries[0] if summaries else ""
    return merged


def _concept(value: Any) -> Concept:
    if isinstance(value, dict):
        return Concept(name=str(value.get("name", "")), description=str(value.get("description", "")))
    return Concept(name=str(value))


def _entity(value: Any) -> Entity:
    if isinstance(value, dict):
        return Entity(name=str(value.get("name", "")), type=str(value.get("type", "concept")))
    return Entity(name=str(value), type="concept")


def _decision(value: Any) -> Decision:
    if isinstance(value, dict):
        return Decision(what=str(value.get("what", "")), why=str(value.get("why", "")), when=str(value.get("when", "")))
    return Decision(what=str(value))


def _action_item(value: Any) -> ActionItem:
    if isinstance(value, dict):
        return ActionItem(task=str(value.get("task", "")), owner=str(value.get("owner", "")), due=str(value.get("due", "")))
    return ActionItem(task=str(value))


def _claim(value: Any) -> Claim:
    if isinstance(value, dict):
        return Claim(text=str(value.get("text", "")), evidence=str(value.get("evidence", "")))
    return Claim(text=str(value))


def _connection(value: Any) -> Connection:
    if isinstance(value, dict):
        return Connection(
            source=str(value.get("source") or value.get("from", "")),
            target=str(value.get("target") or value.get("to", "")),
            relation=str(value.get("relation", "related_to")),
        )
    return Connection(source=str(value), target="")


def _marker(value: Any) -> str:
    if isinstance(value, dict):
        return "|".join(str(value.get(k, "")) for k in sorted(value))
    return str(value)
