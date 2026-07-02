from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _load_dotenv() -> None:
    env_path = Path(os.getenv("PKB_ENV_FILE", Path.cwd() / ".env"))
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = os.path.expandvars(value.strip().strip('"\''))
        os.environ[key] = value


_load_dotenv()


@dataclass
class Settings:
    root_dir: Path = field(default_factory=lambda: Path(os.getenv("PKB_ROOT", Path.cwd())).resolve())
    llm_context_window: int = field(default_factory=lambda: int(os.getenv("PKB_LLM_CONTEXT_WINDOW", "4096")))
    llm_provider: str = field(default_factory=lambda: os.getenv("PKB_LLM_PROVIDER", "local"))
    llm_model: str = field(default_factory=lambda: os.getenv("PKB_LLM_MODEL", "deterministic-local"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("PKB_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("PKB_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    llm_timeout: int = field(default_factory=lambda: int(os.getenv("PKB_LLM_TIMEOUT", "60")))
    llm_model_light: str = field(default_factory=lambda: os.getenv("PKB_LLM_MODEL_LIGHT", ""))
    llm_model_default: str = field(default_factory=lambda: os.getenv("PKB_LLM_MODEL_DEFAULT", ""))
    llm_model_heavy: str = field(default_factory=lambda: os.getenv("PKB_LLM_MODEL_HEAVY", ""))
    llm_cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("PKB_LLM_CACHE_TTL", "3600")))
    llm_cache_enabled: bool = field(default_factory=lambda: os.getenv("PKB_LLM_CACHE_ENABLED", "1") == "1")
    embedding_provider: str = field(default_factory=lambda: os.getenv("PKB_EMBEDDING_PROVIDER", "local"))
    embedding_model: str = field(default_factory=lambda: os.getenv("PKB_EMBEDDING_MODEL", "hashing-local"))
    embedding_dimension: int = field(default_factory=lambda: int(os.getenv("PKB_EMBEDDING_DIMENSION", "64")))
    embedding_api_key: str = field(default_factory=lambda: os.getenv("PKB_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY", ""))
    embedding_base_url: str = field(default_factory=lambda: os.getenv("PKB_EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    embedding_timeout: int = field(default_factory=lambda: int(os.getenv("PKB_EMBEDDING_TIMEOUT", "30")))
    alert_lark_webhook: str = field(default_factory=lambda: os.getenv("PKB_ALERT_LARK_WEBHOOK", ""))
    storage_dir: Path | None = None
    raw_dir: Path | None = None
    parsed_md_dir: Path | None = None
    processed_md_dir: Path | None = None
    wiki_dir: Path | None = None
    index_dir: Path | None = None
    checkpoint_dir: Path | None = None
    log_dir: Path | None = None
    config_dir: Path | None = None
    categories_file: Path | None = None

    def __post_init__(self) -> None:
        self.root_dir = Path(self.root_dir).resolve()
        self.storage_dir = self.storage_dir or self.root_dir / "storage"
        self.raw_dir = self.raw_dir or self.storage_dir / "raw"
        self.parsed_md_dir = self.parsed_md_dir or self.storage_dir / "parsed_md"
        self.processed_md_dir = self.processed_md_dir or self.storage_dir / "processed_md"
        self.wiki_dir = self.wiki_dir or self.storage_dir / "wiki"
        self.index_dir = self.index_dir or self.storage_dir / "index"
        self.checkpoint_dir = self.checkpoint_dir or self.storage_dir / "checkpoints"
        self.log_dir = self.log_dir or self.root_dir / "logs"
        self.config_dir = self.config_dir or self.root_dir / "config"
        self.categories_file = self.categories_file or self.config_dir / "categories.yaml"
        for field_name in (
            "storage_dir",
            "raw_dir",
            "parsed_md_dir",
            "processed_md_dir",
            "wiki_dir",
            "index_dir",
            "checkpoint_dir",
            "log_dir",
            "config_dir",
        ):
            Path(getattr(self, field_name)).mkdir(parents=True, exist_ok=True)


def load_settings(root_dir: str | Path | None = None) -> Settings:
    return Settings(root_dir=Path(root_dir).resolve() if root_dir else Path(os.getenv("PKB_ROOT", Path.cwd())).resolve())


def _simple_yaml_categories(text: str) -> dict[str, list[str]]:
    categories: dict[str, list[str]] = {}
    current: str | None = None
    in_categories = False
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "categories:":
            in_categories = True
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            current = stripped[:-1].strip()
            if current == "categories":
                in_categories = True
                current = None
            else:
                categories.setdefault(current, [])
            continue
        if stripped.startswith("-") and (current or in_categories):
            item = stripped[1:].strip().strip('"\'')
            if current and item:
                categories.setdefault(current, []).append(item)
    return categories


def load_categories(categories_file: str | Path) -> dict[str, list[str]]:
    path = Path(categories_file)
    if not path.exists():
        return {"general": ["知识", "note", "memo", "学习"]}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data: Any = yaml.safe_load(text) or {}
        if isinstance(data, dict) and "categories" in data:
            data = data["categories"]
        if isinstance(data, dict):
            return {str(k): [str(x) for x in (v or [])] for k, v in data.items()}
    except Exception:
        pass
    parsed = _simple_yaml_categories(text)
    return parsed or {"general": ["知识", "note", "memo", "学习"]}
