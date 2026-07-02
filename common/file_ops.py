from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unique_path(directory: str | Path, filename: str) -> Path:
    directory = ensure_dir(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        new_candidate = directory / f"{stem}_{counter}{suffix}"
        if not new_candidate.exists():
            return new_candidate
        counter += 1


def copy_unique(src: str | Path, dest_dir: str | Path) -> Path:
    src_path = Path(src)
    dest = unique_path(dest_dir, src_path.name)
    shutil.copy2(src_path, dest)
    return dest


def download_unique(url: str, dest_dir: str | Path) -> Path:
    parsed = urlparse(url)
    name = Path(parsed.path).name or f"remote_{datetime.now().strftime('%H%M%S')}.bin"
    dest = unique_path(dest_dir, name)
    with urlopen(url, timeout=20) as response:  # nosec - user supplied collection source
        dest.write_bytes(response.read())
    return dest


def read_text(path: str | Path) -> str:
    data = Path(path).read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def write_json(path: str | Path, data: object) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: str | Path, default: object | None = None) -> object:
    p = Path(path)
    if not p.exists():
        return {} if default is None else default
    return json.loads(p.read_text(encoding="utf-8"))
