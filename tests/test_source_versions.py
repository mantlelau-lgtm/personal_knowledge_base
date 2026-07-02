from __future__ import annotations

import time
from pathlib import Path

from sync.source_versions import IncrementalSync


def test_incremental_sync_scan(settings, tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    file_a = root / "a.md"
    file_b = root / "b.txt"
    file_a.write_text("hello world", encoding="utf-8")
    file_b.write_text("second file", encoding="utf-8")

    sync = IncrementalSync(settings)

    first = sync.scan([str(root)])
    assert first["scanned"] == 2
    assert first["changed"] >= 2

    time.sleep(0.01)
    second = sync.scan([str(root)])
    assert second["scanned"] == 2
    assert second["changed"] == 0

    time.sleep(0.01)
    file_a.write_text("hello world updated", encoding="utf-8")
    third = sync.scan([str(root)])
    assert third["changed"] == 1

    changed_paths = sync.get_changed_paths()
    assert str(file_a.resolve()) in changed_paths

    # mark_processed 后 file_a 应从 changed 列表移除
    changed = sync.store.list_changed()
    ids_for_a = [c["source_id"] for c in changed if c["path"] == str(file_a.resolve())]
    sync.mark_processed(ids_for_a)

    remaining = sync.get_changed_paths()
    assert str(file_a.resolve()) not in remaining
