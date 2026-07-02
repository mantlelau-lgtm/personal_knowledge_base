from __future__ import annotations

from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from content_refinement.refiner import ContentRefiner
from data_collection.collector import DataCollector
from data_parsing.processor import MarkdownProcessor

from .store import JobStore


class JobRunner:
    def __init__(self, settings: Settings | None = None, store: JobStore | None = None) -> None:
        self.settings = settings or load_settings()
        self.store = store or JobStore(self.settings)

    def run_distill(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        if job.type != "distill":
            raise ValueError(f"unsupported job type: {job.type}")

        acquired = self.store.acquire_lease(job_id, seconds=900)
        if not acquired:
            return self.store.to_dict(self.store.get_job(job_id))

        try:
            self.store.update_job(job_id, status="running", stage="collecting", current=0, total=4, error="")
            self.store.add_event(job_id, "info", "collecting", "开始采集文档")
            sources = [str(x) for x in job.input.get("sources", [])]
            collected = DataCollector(self.settings).collect(sources) if sources else []
            self.store.update_job(job_id, stage="extracting", current=1)
            self.store.add_event(job_id, "info", "collected", f"采集完成：{len(collected)} 个文件")

            processed = MarkdownProcessor(self.settings).process_all()
            self.store.update_job(job_id, stage="writing", current=2)
            self.store.add_event(job_id, "info", "processed", f"解析提炼完成：{len(processed)} 个文件")

            refined = ContentRefiner(self.settings).refine_all()
            self.store.update_job(job_id, stage="done", current=4, status="done", result={
                "collected": [r.__dict__ for r in collected],
                "processed": [r.__dict__ for r in processed],
                "refined": [r.__dict__ for r in refined],
            })
            self.store.add_event(job_id, "info", "done", f"蒸馏完成：生成/更新 {len(refined)} 个 Wiki 文档")
            return self.store.to_dict(self.store.get_job(job_id))
        except Exception as exc:
            latest = self.store.get_job(job_id)
            retry_count = (latest.retry_count if latest else 0) + 1
            status = "dead" if latest and retry_count > latest.max_retries else "failed"
            self.store.update_job(job_id, status=status, error=str(exc), retry_count=retry_count)
            self.store.add_event(job_id, "error", "failed", str(exc), {"type": exc.__class__.__name__})
            raise
        finally:
            self.store.release_lease(job_id)

    def retry(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        self.store.update_job(job_id, status="pending", stage="pending", error="")
        self.store.add_event(job_id, "info", "retry", "任务已重新提交")
        return self.run_distill(job_id)
