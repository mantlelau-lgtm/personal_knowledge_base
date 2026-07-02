from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from common.config import Settings, load_settings


@dataclass
class PromptRegistry:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.prompt_dir = Path(self.settings.root_dir) / "prompts"

    def get(self, name: str, version: str = "v1") -> str:
        path = self.prompt_dir / f"{name}_{version}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def render(self, name: str, version: str = "v1", **kwargs: str) -> str:
        template = self.get(name, version)
        for key, value in kwargs.items():
            template = template.replace("{{" + key + "}}", value)
        return template

    def available_versions(self, name: str) -> list[str]:
        if not self.prompt_dir.exists():
            return []
        versions: list[str] = []
        pattern = re.compile(rf"^{re.escape(name)}_(?P<version>[^.]+)\.md$")
        for path in sorted(self.prompt_dir.glob(f"{name}_*.md")):
            match = pattern.match(path.name)
            if match:
                versions.append(match.group("version"))
        return versions

    def list_prompts(self) -> list[dict]:
        if not self.prompt_dir.exists():
            return []
        buckets: dict[str, list[str]] = {}
        pattern = re.compile(r"^(?P<name>.+)_(?P<version>[^_.]+)\.md$")
        for path in sorted(self.prompt_dir.glob("*.md")):
            match = pattern.match(path.name)
            if not match:
                continue
            buckets.setdefault(match.group("name"), []).append(match.group("version"))
        return [{"name": name, "versions": sorted(versions)} for name, versions in sorted(buckets.items())]
