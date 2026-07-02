from pathlib import Path

import pytest

from common.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "categories.yaml").write_text(
        "categories:\n  python:\n    - Python\n    - pytest\n  ai:\n    - RAG\n    - LLM\n",
        encoding="utf-8",
    )
    return Settings(
        root_dir=tmp_path,
        config_dir=config_dir,
        categories_file=config_dir / "categories.yaml",
        llm_provider="local",
        llm_model="deterministic-local",
        embedding_provider="local",
        embedding_model="hashing-local",
    )
