from __future__ import annotations

from alerts.alerter import Alerter
from alerts.notifiers import LarkBotNotifier, LogNotifier
from alerts.store import AlertStore


def test_alert_store_lifecycle(settings):
    store = AlertStore(settings)

    a1 = store.create("P1", "boot_failed", "启动失败", {"trace": "x"})
    a2 = store.create("P2", "slow_llm", "LLM 慢")
    store.create("INFO", "hello", "info msg")

    assert a1["level"] == "P1"
    assert a1["resolved"] is False
    assert a1["data"] == {"trace": "x"}

    all_alerts = store.list()
    assert len(all_alerts) == 3

    p1_only = store.list(level="P1")
    assert len(p1_only) == 1 and p1_only[0]["id"] == a1["id"]

    open_only = store.list(resolved=False)
    assert len(open_only) == 3

    store.resolve(a2["id"])
    open_after = store.list(resolved=False)
    resolved = store.list(resolved=True)
    assert len(open_after) == 2
    assert len(resolved) == 1 and resolved[0]["id"] == a2["id"]

    stats = store.stats()
    assert stats["open_total"] == 2
    assert stats["open_by_level"]["P1"] == 1
    assert stats["open_by_level"]["P2"] == 0
    assert stats["open_by_level"]["INFO"] == 1


def test_alerter_log_notifier(settings):
    alerter = Alerter(settings)
    record = alerter.p1("test", "hello", {"a": 1})
    assert isinstance(record, dict)
    assert record["level"] == "P1"
    assert record["event"] == "test"
    assert record["message"] == "hello"
    assert record["data"] == {"a": 1}
    assert record["resolved"] is False

    recent = alerter.recent()
    assert any(r["id"] == record["id"] for r in recent)


def test_alerter_lark_notifier_skipped(settings):
    settings.alert_lark_webhook = ""
    alerter = Alerter(settings)
    assert len(alerter.notifiers) == 1
    assert isinstance(alerter.notifiers[0], LogNotifier)
    assert not any(isinstance(n, LarkBotNotifier) for n in alerter.notifiers)
