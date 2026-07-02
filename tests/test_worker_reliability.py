from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from jobs.circuit_breaker import CircuitBreaker
from jobs.recovery import RecoveryService
from jobs.store import JobStore


UTC = timezone.utc


def test_acquire_and_release_lease(settings):
    store = JobStore(settings)
    job = store.create_job("distill", {"sources": []})

    acquired = store.acquire_lease(job.id, seconds=300)
    assert acquired is not None
    assert acquired.status == "running"
    assert acquired.lease_until != ""

    fetched = store.get_job(job.id)
    assert fetched.status == "running"
    assert fetched.lease_until != ""

    store.release_lease(job.id)
    released = store.get_job(job.id)
    assert released.lease_until == ""


def test_recovery_stale_jobs(settings):
    store = JobStore(settings)
    job = store.create_job("distill", {"sources": []})
    acquired = store.acquire_lease(job.id, seconds=300)
    assert acquired is not None

    past = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
    store.update_job(job.id, lease_until=past)

    recovered = RecoveryService(settings, store).recover_stale_jobs()
    assert job.id in recovered

    refreshed = store.get_job(job.id)
    assert refreshed.status == "pending"
    assert refreshed.lease_until == ""


def test_circuit_breaker():
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=1)

    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.allow() is False

    time.sleep(1.1)
    assert breaker.allow() is True  # half-open
    breaker.record_success()
    assert breaker.allow() is True
