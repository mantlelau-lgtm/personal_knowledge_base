from __future__ import annotations

import re


def split_markdown_chunks(text: str, max_chars: int = 900) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    heading = "正文"
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip()
        if not content:
            buffer = []
            return
        for part in _split_long(content, max_chars):
            chunks.append({"heading": heading, "text": part})
        buffer = []

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            flush()
            heading = match.group(2).strip()
            buffer.append(line)
        else:
            buffer.append(line)
    flush()
    return chunks or [{"heading": heading, "text": text[:max_chars]}]


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                parts.append(current.strip())
                current = ""
            for i in range(0, len(paragraph), max_chars):
                parts.append(paragraph[i : i + max_chars])
        elif len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}" if current else paragraph
        else:
            parts.append(current.strip())
            current = paragraph
    if current:
        parts.append(current.strip())
    return parts
