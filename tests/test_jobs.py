from pathlib import Path

from jobs.runner import JobRunner
from jobs.store import JobStore


def test_job_store_create_update_events(settings):
    store = JobStore(settings)
    job = store.create_job("distill", {"sources": []})
    assert job.status == "pending"

    updated = store.update_job(job.id, status="running", stage="extracting", current=1, total=4)
    assert updated.status == "running"
    assert updated.stage == "extracting"

    store.add_event(job.id, "info", "unit", "测试事件", {"value": 1})
    events = store.list_events(job.id)
    assert events[-1]["message"] == "测试事件"
    assert events[-1]["data"]["value"] == 1


def test_distill_job_runner(settings, tmp_path):
    source = tmp_path / "job_note.txt"
    source.write_text("Python RAG job runner test", encoding="utf-8")

    store = JobStore(settings)
    job = store.create_job("distill", {"sources": [str(source)]})
    result = JobRunner(settings, store).run_distill(job.id)

    assert result["status"] == "done"
    assert result["stage"] == "done"
    assert result["result"]["collected"]
    assert result["result"]["processed"]
    assert result["result"]["refined"]
    assert list(Path(settings.wiki_dir).glob("**/*.md"))
