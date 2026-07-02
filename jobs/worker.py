from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from .circuit_breaker import CircuitBreaker


class JobWorker:
    def __init__(self, max_workers: int = 2) -> None:
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pkb-job")
        self.futures: dict[str, Future] = {}
        self.breaker = CircuitBreaker()

    def submit(self, job_id: str, fn: Callable[[], object]) -> None:
        if job_id in self.futures and not self.futures[job_id].done():
            return
        self.futures[job_id] = self.executor.submit(fn)

    def submit_with_breaker(self, job_id: str, fn: Callable[[], object]) -> None:
        if job_id in self.futures and not self.futures[job_id].done():
            return

        def wrapper() -> object:
            if not self.breaker.allow():
                self._mark_breaker_failure(job_id)
                raise RuntimeError("circuit breaker is open")
            try:
                result = fn()
            except Exception:
                self.breaker.record_failure()
                raise
            self.breaker.record_success()
            return result

        self.futures[job_id] = self.executor.submit(wrapper)

    def _mark_breaker_failure(self, job_id: str) -> None:
        try:
            from .store import JobStore

            store = JobStore()
            job = store.get_job(job_id)
            if job:
                store.update_job(job_id, status="failed", error="circuit breaker is open")
                store.add_event(job_id, "error", "breaker_open", "断路器打开，任务被拒绝")
        except Exception:
            pass

    def is_running(self, job_id: str) -> bool:
        future = self.futures.get(job_id)
        return bool(future and not future.done())
