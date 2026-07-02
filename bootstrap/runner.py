from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.config import Settings, load_settings
from jobs.runner import JobRunner
from jobs.store import JobStore

from .store import BootstrapStore


@dataclass
class BootstrapRunner:
    settings: Settings | None = None
    store: BootstrapStore | None = None
    job_store: JobStore | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.store = self.store or BootstrapStore(self.settings)
        self.job_store = self.job_store or JobStore(self.settings)

    def execute(self, plan_id: str, batch_size: int = 5) -> dict[str, Any]:
        plan = self.store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"plan not found: {plan_id}")
        if plan["status"] != "approved":
            raise ValueError(f"plan status must be approved, got: {plan['status']}")
        self.store.update_plan(plan_id, status="running")

        sources = list(plan.get("sources", []))
        batches = [sources[i : i + batch_size] for i in range(0, len(sources), batch_size)] or [[]]
        job_ids: list[str] = []
        runner = JobRunner(self.settings, self.job_store)
        try:
            for batch in batches:
                job = self.job_store.create_job("distill", {"sources": batch, "bootstrap_plan": plan_id})
                job_ids.append(job.id)
                runner.run_distill(job.id)
            return self.store.update_plan(plan_id, status="done", job_ids=job_ids)
        except Exception as exc:
            self.store.update_plan(plan_id, status="failed", job_ids=job_ids, approved_by=f"error: {exc}")
            raise
