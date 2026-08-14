from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from dataclasses import asdict, dataclass, field

from filesync.paths import normalize_relpath

MANIFEST_NAME = ".filesync-manifest.json"


@dataclass
class FileRecord:
    size: int
    mtime: int
    atime: int
    birth: int
    times_known: bool = True


@dataclass
class Manifest:
    version: int
    source: dict
    files: dict[str, FileRecord] = field(default_factory=dict)


def empty_manifest(source: dict | None = None) -> Manifest:
    return Manifest(version=1, source=source or {}, files={})


def load_manifest(directory: str) -> Manifest | None:
    """Load `.filesync-manifest.json`, or None if it is missing or unreadable."""
    path = os.path.join(directory, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        files = {
            normalize_relpath(key): FileRecord(
                size=int(value["size"]),
                mtime=int(value["mtime"]),
                atime=int(value["atime"]),
                birth=int(value.get("birth", 0)),
                times_known=bool(value.get("times_known", True)),
            )
            for key, value in raw.get("files", {}).items()
        }
        return Manifest(version=int(raw.get("version", 1)), source=raw.get("source") or {}, files=files)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_manifest(directory: str, manifest: Manifest) -> None:
    """Write the manifest atomically.

    We write to a sibling temp file in the same directory and then
    `os.replace` it over the real path, so a crash or power loss mid-write
    can never leave a truncated/corrupt manifest on disk (the old manifest,
    if any, stays intact until the new one is fully written).
    """
    os.makedirs(directory, exist_ok=True)
    payload = {
        "version": manifest.version,
        "source": manifest.source,
        "files": {key: asdict(record) for key, record in manifest.files.items()},
    }
    path = os.path.join(directory, MANIFEST_NAME)
    fd, tmp_path = tempfile.mkstemp(prefix="filesync-manifest-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp_path, path)
        tmp_path = ""
    except BaseException:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _replace_with_retry(src: str, dst: str, attempts: int = 8) -> None:
    """Windows often locks .json files (Defender, indexing). Retry replace."""
    delay = 0.05
    last_error: OSError | None = None
    for _ in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            last_error = exc
            try:
                if os.path.exists(dst):
                    os.chmod(dst, stat.S_IWRITE)
            except OSError:
                pass
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
    if last_error is not None:
        raise last_error
    os.replace(src, dst)


def upsert_file(manifest: Manifest, relpath: str, record: FileRecord) -> None:
    manifest.files[normalize_relpath(relpath)] = record


def record_for(relpath: str, source_manifest: Manifest | None, captured: FileRecord) -> FileRecord:
    """Manifest is the source of truth for dates.

    If the manifest is missing, this file is not in it, or the stored
    times are unknown, use `captured` (Windows file dates for a PC source).
    Live size always comes from `captured`.
    """
    key = normalize_relpath(relpath)
    if source_manifest and key in source_manifest.files:
        original = source_manifest.files[key]
        if original.times_known:
            return FileRecord(
                size=captured.size,
                mtime=original.mtime,
                atime=original.atime,
                birth=original.birth,
                times_known=True,
            )
    return captured
