from __future__ import annotations

from common.llm_gateway import LLMGateway
from metrics.daily import DailyStatsAggregator


def test_daily_aggregate_and_list(settings):
    gateway = LLMGateway(settings)
    gateway.record_call("local", "deterministic-local", "summarize:v1", lambda: "回答1", prompt_tokens=10)
    gateway.record_call("local", "deterministic-local", "chat:v1", lambda: "回答2", prompt_tokens=20)
    gateway.record_call("local", "deterministic-local", "extract:v1", lambda: "回答3", prompt_tokens=15)

    agg = DailyStatsAggregator(settings)
    result = agg.aggregate()
    assert result["total_calls"] >= 3
    assert result["total_prompt_tokens"] >= 45
    assert result["error_count"] == 0
    assert result["purpose_breakdown"]
    assert "summarize:v1" in result["purpose_breakdown"]
    assert result["purpose_breakdown"]["summarize:v1"]["calls"] >= 1

    recent = agg.list_recent(7)
    assert recent
    assert recent[0]["total_calls"] >= 3
    assert isinstance(recent[0]["purpose_breakdown"], dict)


def test_daily_aggregate_specific_day(settings):
    agg = DailyStatsAggregator(settings)
    result = agg.aggregate(day="2000-01-01")
    assert result["day"] == "2000-01-01"
    assert result["total_calls"] == 0
