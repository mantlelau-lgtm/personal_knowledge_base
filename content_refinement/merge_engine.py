from __future__ import annotations

from typing import Any

from data_parsing.extract_schema import merge_extracted_knowledge, normalize_extracted_knowledge
from data_parsing.processor import parse_front_matter


def merge_metadata(existing_text: str, incoming_metadata: dict[str, Any]) -> dict[str, Any]:
    existing_metadata, _ = parse_front_matter(existing_text)
    existing_knowledge = existing_metadata.get("knowledge") or {
        "core_topic": existing_metadata.get("core_topic", ""),
        "key_points": existing_metadata.get("key_points", []),
        "related_entities": existing_metadata.get("related_entities", []),
    }
    incoming_knowledge = incoming_metadata.get("knowledge") or {
        "core_topic": incoming_metadata.get("core_topic", ""),
        "key_points": incoming_metadata.get("key_points", []),
        "related_entities": incoming_metadata.get("related_entities", []),
    }
    knowledge = merge_extracted_knowledge([existing_knowledge, incoming_knowledge])
    core_topic = str(existing_metadata.get("core_topic") or incoming_metadata.get("core_topic") or knowledge.get("summary") or "untitled")
    return {
        "source_file": existing_metadata.get("source_file") or incoming_metadata.get("source_file", ""),
        "core_topic": core_topic,
        "key_points": [claim.get("text", "") for claim in knowledge.get("claims", []) if claim.get("text")][:20],
        "related_entities": [entity.get("name", "") for entity in knowledge.get("entities", []) if entity.get("name")][:30],
        "knowledge": normalize_extracted_knowledge(knowledge),
    }
