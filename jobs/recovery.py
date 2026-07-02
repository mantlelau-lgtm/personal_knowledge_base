from __future__ import annotations

from datetime import datetime, timezone

from common.config import Settings, load_settings

from .store import JobStore


UTC = timezone.utc


class RecoveryService:
    def __init__(self, settings: Settings | None = None, store: JobStore | None = None) -> None:
        self.settings = settings or load_settings()
        self.store = store or JobStore(self.settings)

    def recover_stale_jobs(self) -> list[str]:
        now = datetime.now(UTC).isoformat()
        recovered: list[str] = []
        for job in self.store.list_pending_or_stale(now):
            if job.status == "running":
                self.store.add_event(
                    job.id,
                    "warning",
                    "lease_expired_recover",
                    "任务租约过期，已恢复为 pending",
                    {"lease_until": job.lease_until},
                )
                self.store.update_job(job.id, status="pending", lease_until="")
                recovered.append(job.id)
        return recovered


def recover_on_startup(settings: Settings | None = None) -> list[str]:
    return RecoveryService(settings).recover_stale_jobs()
