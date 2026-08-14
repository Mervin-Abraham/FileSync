import json
import os
from pathlib import Path

import pytest

from filesync.manifest import (
    MANIFEST_NAME,
    FileRecord,
    empty_manifest,
    load_manifest,
    record_for,
    save_manifest,
    upsert_file,
)


def test_round_trip(tmp_path: Path):
    manifest = empty_manifest({"kind": "mtp", "path": "/sdcard/DCIM", "device": "SERIAL"})
    upsert_file(
        manifest,
        r"Camera\IMG_001.jpg",
        FileRecord(size=10, mtime=1700000123, atime=1700000123, birth=0),
    )
    save_manifest(str(tmp_path), manifest)

    loaded = load_manifest(str(tmp_path))
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.source["kind"] == "mtp"
    assert "Camera/IMG_001.jpg" in loaded.files
    rec = loaded.files["Camera/IMG_001.jpg"]
    assert rec.mtime == 1700000123
    assert rec.birth == 0
    on_disk = json.loads((tmp_path / ".filesync-manifest.json").read_text())
    assert on_disk["files"]["Camera/IMG_001.jpg"]["mtime"] == 1700000123


def test_missing_manifest_returns_none(tmp_path: Path):
    assert load_manifest(str(tmp_path)) is None


def test_corrupt_manifest_returns_none(tmp_path: Path):
    (tmp_path / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert load_manifest(str(tmp_path)) is None


def test_record_for_prefers_source_manifest_times():
    source = empty_manifest()
    upsert_file(
        source,
        "Camera/a.jpg",
        FileRecord(size=1, mtime=111, atime=111, birth=0),
    )
    captured = FileRecord(size=999, mtime=222, atime=222, birth=0)
    chosen = record_for("Camera/a.jpg", source, captured)
    assert chosen.mtime == 111
    assert chosen.atime == 111
    assert chosen.size == 999


def test_record_for_uses_captured_when_absent():
    captured = FileRecord(size=5, mtime=333, atime=333, birth=0)
    chosen = record_for("other.jpg", empty_manifest(), captured)
    assert chosen == captured


def test_record_for_uses_captured_when_manifest_is_missing():
    captured = FileRecord(size=5, mtime=333, atime=333, birth=0)
    chosen = record_for("pic.jpg", None, captured)
    assert chosen == captured


def test_record_for_uses_captured_when_manifest_times_unknown():
    source = empty_manifest()
    upsert_file(
        source,
        "pic.jpg",
        FileRecord(size=1, mtime=0, atime=0, birth=0, times_known=False),
    )
    captured = FileRecord(size=5, mtime=333, atime=333, birth=0)
    chosen = record_for("pic.jpg", source, captured)
    assert chosen == captured


def test_save_manifest_leaves_original_intact_if_write_crashes(tmp_path: Path, monkeypatch):
    """A crash mid-write must not corrupt/truncate the existing manifest:
    save_manifest writes to a sibling temp file and only os.replace()s it
    over the real path once the write has fully succeeded."""
    original = empty_manifest({"kind": "local"})
    upsert_file(original, "a.jpg", FileRecord(size=1, mtime=100, atime=100, birth=0))
    save_manifest(str(tmp_path), original)
    original_bytes = (tmp_path / MANIFEST_NAME).read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", boom)
    updated = empty_manifest({"kind": "local"})
    upsert_file(updated, "b.jpg", FileRecord(size=2, mtime=200, atime=200, birth=0))
    with pytest.raises(OSError):
        save_manifest(str(tmp_path), updated)

    assert (tmp_path / MANIFEST_NAME).read_bytes() == original_bytes
    # no leftover temp file from the aborted write
    assert list(tmp_path.iterdir()) == [tmp_path / MANIFEST_NAME]


def test_save_manifest_retries_access_denied(tmp_path: Path, monkeypatch):
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr("filesync.manifest.time.sleep", lambda _t: None)
    save_manifest(str(tmp_path), empty_manifest({"kind": "local"}))
    assert calls["n"] == 3
    assert load_manifest(str(tmp_path)) is not None


def test_save_manifest_uses_replace_not_truncating_write(tmp_path: Path, monkeypatch):
    """Guard against a regression to `open(path, 'w')`, which truncates the
    destination file before the new content is fully written."""
    calls = []
    real_replace = os.replace

    def tracking_replace(src, dst):
        calls.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracking_replace)
    manifest = empty_manifest({"kind": "local"})
    save_manifest(str(tmp_path), manifest)

    assert len(calls) == 1
    src, dst = calls[0]
    assert dst == str(tmp_path / MANIFEST_NAME)
    assert src != dst
    assert os.path.dirname(src) == str(tmp_path)
