from __future__ import annotations

from typing import Any

from common.config import Settings, load_settings

from .notifiers import LarkBotNotifier, LogNotifier, Notifier
from .store import AlertStore


class Alerter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.store = AlertStore(self.settings)
        self.notifiers: list[Notifier] = [LogNotifier(self.settings)]
        webhook = getattr(self.settings, "alert_lark_webhook", "") or ""
        if webhook:
            self.notifiers.append(LarkBotNotifier(webhook))

    def alert(self, level: str, event: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self.store.create(level, event, message, data)
        for notifier in self.notifiers:
            try:
                notifier.notify(record)
            except Exception:
                continue
        return record

    def p1(self, event: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.alert("P1", event, message, data)

    def p2(self, event: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.alert("P2", event, message, data)

    def info(self, event: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.alert("INFO", event, message, data)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list(limit=limit)
