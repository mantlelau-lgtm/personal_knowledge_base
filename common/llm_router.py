from __future__ import annotations

from dataclasses import dataclass

from common.config import Settings, load_settings


@dataclass
class ModelRouter:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()

    def _fallback(self) -> str:
        return getattr(self.settings, "llm_model", "") or "deterministic-local"

    def _light(self) -> str:
        return getattr(self.settings, "llm_model_light", "") or self._fallback()

    def _default(self) -> str:
        return getattr(self.settings, "llm_model_default", "") or self._fallback()

    def _heavy(self) -> str:
        return getattr(self.settings, "llm_model_heavy", "") or self._fallback()

    def pick(self, purpose: str) -> str:
        purpose = (purpose or "").lower()
        if purpose in {"summarize", "extract"}:
            return self._light()
        if purpose in {"iterative", "complex"}:
            return self._heavy()
        return self._default()

    def describe(self) -> dict:
        return {
            "light": self._light(),
            "default": self._default(),
            "heavy": self._heavy(),
        }
