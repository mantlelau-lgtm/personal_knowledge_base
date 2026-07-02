from __future__ import annotations

import json
import urllib.request
from typing import Any

from common.config import Settings, load_settings
from common.logging_config import setup_logger


class Notifier:
    def notify(self, alert: dict[str, Any]) -> bool:
        raise NotImplementedError


class LogNotifier(Notifier):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.logger = setup_logger("alerts", self.settings)

    def notify(self, alert: dict[str, Any]) -> bool:
        level = str(alert.get("level", "INFO")).upper()
        message = f"[{alert.get('level')}] {alert.get('event')}: {alert.get('message')}"
        if level == "P1":
            self.logger.error(message)
        elif level == "P2":
            self.logger.warning(message)
        else:
            self.logger.info(message)
        return True


class LarkBotNotifier(Notifier):
    def __init__(self, webhook_url: str, timeout: float = 5.0) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    def notify(self, alert: dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False
        payload = {
            "msg_type": "text",
            "content": {
                "text": f"[{alert.get('level')}] {alert.get('event')}: {alert.get('message')}"
            },
        }
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False
