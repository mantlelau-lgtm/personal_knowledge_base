from pathlib import Path

from bootstrap.estimator import CostEstimator
from bootstrap.runner import BootstrapRunner
from bootstrap.store import BootstrapStore


def _make_sources(tmp_path: Path) -> Path:
    src = tmp_path / "bootstrap_src"
    src.mkdir()
    (src / "a.md").write_text("# A\n\n" + "python rag " * 30, encoding="utf-8")
    (src / "b.txt").write_text("bootstrap sample text " * 20, encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "c.md").write_text("# C\n\n知识库测试", encoding="utf-8")
    return src


def test_bootstrap_store_lifecycle(settings, tmp_path):
    store = BootstrapStore(settings)
    plan = store.create_plan("first", ["/tmp/x"])
    assert plan["status"] == "draft"
    got = store.get_plan(plan["id"])
    assert got and got["name"] == "first"
    updated = store.update_plan(plan["id"], status="approved", approved_by="admin")
    assert updated["status"] == "approved"
    plans = store.list_plans(10)
    assert any(p["id"] == plan["id"] for p in plans)
    store.delete_plan(plan["id"])
    assert store.get_plan(plan["id"]) is None


def test_cost_estimator(settings, tmp_path):
    src = _make_sources(tmp_path)
    estimation = CostEstimator(settings).estimate([str(src)])
    assert estimation["total_files"] == 3
    assert estimation["total_chars"] > 0
    assert estimation["estimated_tokens"] >= 1
    assert estimation["estimated_cost_usd"] >= 0


def test_bootstrap_runner_execute(settings, tmp_path):
    src = _make_sources(tmp_path)
    store = BootstrapStore(settings)
    plan = store.create_plan("run", [str(src)])
    estimation = CostEstimator(settings).estimate(plan["sources"])
    store.update_plan(
        plan["id"],
        status="approved",
        total_files=estimation["total_files"],
        total_chars=estimation["total_chars"],
        estimated_tokens=estimation["estimated_tokens"],
        estimated_cost_usd=estimation["estimated_cost_usd"],
        approved_by="admin",
    )
    result = BootstrapRunner(settings).execute(plan["id"], batch_size=2)
    assert result["status"] == "done"
    assert result["job_ids"]
