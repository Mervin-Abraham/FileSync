from pathlib import Path

import pytest

from filesync.copy import Endpoint, dest_prefix_for, same_size, sync_directories
from filesync.manifest import (
    MANIFEST_NAME,
    FileRecord,
    empty_manifest,
    load_manifest,
    save_manifest,
    upsert_file,
)
from filesync.times import FileTimes, read_local_times, write_local_times


def _counts(**kwargs):
    base = {
        "copied": 0,
        "skipped": 0,
        "failed": 0,
        "ignored": 0,
        "copied_bytes": 0,
        "skipped_bytes": 0,
        "failed_bytes": 0,
        "stopped": False,
        "error": "",
        "elapsed_seconds": 0.0,
    }
    base.update(kwargs)
    return base


def _without_elapsed(result: dict) -> dict:
    data = dict(result)
    data["elapsed_seconds"] = 0.0
    return data


def test_same_size_only_when_equal():
    assert same_size(10, 10) is True
    assert same_size(None, 10) is False
    assert same_size(9, 10) is False


def test_rejects_identical_local_paths(tmp_path: Path):
    endpoint = Endpoint(kind="local", path=str(tmp_path))
    with pytest.raises(ValueError, match="same"):
        sync_directories(endpoint, endpoint, adb=None, logger=None)


def test_local_sync_writes_manifest_and_mtime(tmp_path: Path):
    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    photo = src / "Camera" / "pic.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"hello")
    write_local_times(str(photo), FileTimes(mtime=1700000123, atime=1700000123, birth=0))

    result = sync_directories(
        Endpoint(kind="local", path=str(src)),
        Endpoint(kind="local", path=str(dst)),
        adb=None,
        logger=None,
    )
    copied = dst / "Camera" / "pic.jpg"
    assert copied.read_bytes() == b"hello"
    assert result["copied"] == 1
    assert abs(read_local_times(str(copied)).mtime - 1700000123) <= 2
    manifest = load_manifest(str(dst))
    assert manifest is not None
    assert manifest.files["Camera/pic.jpg"].mtime == 1700000123


def test_second_run_skips_same_size(tmp_path: Path):
    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "f.bin").write_bytes(b"xyz")
    sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)
    result = sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)
    assert result["skipped"] == 1
    assert result["copied"] == 0


def test_failed_copy_does_not_enter_manifest(tmp_path: Path, monkeypatch):
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "f.bin").write_bytes(b"xyz")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(copy_mod.shutil, "copy2", boom)
    result = sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)
    assert result["failed"] == 1
    assert load_manifest(str(dst)) is None or "f.bin" not in (load_manifest(str(dst)).files if load_manifest(str(dst)) else {})
    assert not (dst / "f.bin").exists()


def test_capture_failure_still_copies_bytes(tmp_path: Path, monkeypatch):
    """If Android stat fails, still pull the file. Do not stamp 1970 or
    write fake times into the dest manifest."""
    import filesync.copy as copy_mod

    dst = tmp_path / "b"
    dst.mkdir()

    def fake_pull(_adb, _serial, _remote, local):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(b"abc")

    monkeypatch.setattr(copy_mod, "list_remote_files", lambda *a, **k: ["f.bin"])
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: 3)
    monkeypatch.setattr(copy_mod, "read_android_times", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "pull", fake_pull)

    source = Endpoint(kind="mtp", path="/sdcard/Src", device="SERIAL")
    dest = Endpoint(kind="local", path=str(dst))

    result = sync_directories(source, dest, adb="adb", logger=None)

    assert _without_elapsed(result) == _counts(copied=1, copied_bytes=3)
    assert (dst / "f.bin").read_bytes() == b"abc"
    manifest = load_manifest(str(dst))
    assert manifest is None or "f.bin" not in manifest.files


def test_apply_times_failure_on_skip_path_is_caught_and_counted(tmp_path: Path, monkeypatch):
    """Widened per-file try must also cover apply_times on the
    already-same-size (skip) branch, not just copy_bytes."""
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "f.bin").write_bytes(b"xyz")
    (dst / "f.bin").write_bytes(b"xyz")

    def boom(*_args, **_kwargs):
        raise OSError("cannot set times")

    monkeypatch.setattr(copy_mod, "write_local_times", boom)

    result = sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)

    assert _without_elapsed(result) == _counts(skipped=1, skipped_bytes=3)


def test_apply_times_failure_after_copy_is_caught_and_counted(tmp_path: Path, monkeypatch):
    """Widened per-file try must also cover apply_times after a successful
    copy_bytes, so a device-side touch failure doesn't crash the run."""
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    src.mkdir()
    (src / "f.bin").write_bytes(b"xyz")

    def boom(*_args, **_kwargs):
        raise RuntimeError("touch failed on device")

    monkeypatch.setattr(copy_mod, "push", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "ensure_remote_parent", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "remote_exists", lambda *a, **k: False)
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "write_android_times", boom)

    source = Endpoint(kind="local", path=str(src))
    dest = Endpoint(kind="mtp", path="/sdcard/Dest", device="SERIAL")

    result = sync_directories(source, dest, adb="adb", logger=None, mtp_manifest_dir=str(tmp_path / "logs"))

    assert _without_elapsed(result) == _counts(copied=1, copied_bytes=3)


def test_local_to_mtp_pushes_and_applies_times(tmp_path: Path, monkeypatch):
    """Mocked MTP test: local -> mtp push, then touch (write_android_times)."""
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    src.mkdir()
    (src / "f.bin").write_bytes(b"xyz")

    pushed = []
    touched = []

    monkeypatch.setattr(copy_mod, "push", lambda adb, serial, local, remote: pushed.append((local, remote)))
    monkeypatch.setattr(copy_mod, "ensure_remote_parent", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "remote_exists", lambda *a, **k: False)
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: None)
    monkeypatch.setattr(
        copy_mod, "write_android_times", lambda adb, serial, remote, times: touched.append((remote, times))
    )

    source = Endpoint(kind="local", path=str(src))
    dest = Endpoint(kind="mtp", path="/sdcard/Dest", device="SERIAL")

    result = sync_directories(source, dest, adb="adb", logger=None, mtp_manifest_dir=str(tmp_path / "logs"))

    assert _without_elapsed(result) == _counts(copied=1, copied_bytes=3)
    assert pushed == [(str(src / "f.bin"), "/sdcard/Dest/f.bin")]
    assert len(touched) == 1
    assert touched[0][0] == "/sdcard/Dest/f.bin"


def test_local_to_mtp_without_manifest_uses_pc_file_times(tmp_path: Path, monkeypatch):
    """Hop 2 still stamps the dates currently on the PC files if the
    user deleted .filesync-manifest.json."""
    import filesync.copy as copy_mod

    src = tmp_path / "Phone Backup"
    src.mkdir()
    photo = src / "DCIM" / "Camera" / "pic.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"xyz")
    write_local_times(str(photo), FileTimes(mtime=1700000123, atime=1700000100, birth=1700000000))
    assert not (src / MANIFEST_NAME).exists()

    touched = []
    monkeypatch.setattr(copy_mod, "push", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "ensure_remote_parent", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "remote_exists", lambda *a, **k: False)
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: None)
    monkeypatch.setattr(
        copy_mod, "write_android_times", lambda adb, serial, remote, times: touched.append((remote, times))
    )

    source = Endpoint(kind="local", path=str(src))
    dest = Endpoint(kind="mtp", path="/sdcard/", device="SERIAL")
    assert dest_prefix_for(source) == ""

    result = sync_directories(
        source,
        dest,
        adb="adb",
        logger=None,
        dest_prefix=dest_prefix_for(source),
        mtp_manifest_dir=str(tmp_path / "logs"),
    )

    assert result["copied"] == 1
    assert len(touched) == 1
    assert touched[0][0] == "/sdcard/DCIM/Camera/pic.jpg"
    assert touched[0][1].mtime == 1700000123
    assert touched[0][1].atime == 1700000100
    assert touched[0][1].birth == 1700000000


def test_local_to_mtp_prefers_manifest_times_over_windows_dates(tmp_path: Path, monkeypatch):
    """Manifest is the source of truth even if Windows dates were rewritten."""
    import filesync.copy as copy_mod

    src = tmp_path / "Phone Backup"
    src.mkdir()
    photo = src / "DCIM" / "Camera" / "pic.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"xyz")
    write_local_times(str(photo), FileTimes(mtime=1999999999, atime=1999999999, birth=1999999999))
    manifest = empty_manifest({"kind": "mtp"})
    upsert_file(
        manifest,
        "DCIM/Camera/pic.jpg",
        FileRecord(size=3, mtime=1700000123, atime=1700000100, birth=1700000000),
    )
    save_manifest(str(src), manifest)

    touched = []
    monkeypatch.setattr(copy_mod, "push", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "ensure_remote_parent", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "remote_exists", lambda *a, **k: False)
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: None)
    monkeypatch.setattr(
        copy_mod, "write_android_times", lambda adb, serial, remote, times: touched.append((remote, times))
    )

    source = Endpoint(kind="local", path=str(src))
    result = sync_directories(
        source,
        Endpoint(kind="mtp", path="/sdcard/", device="SERIAL"),
        adb="adb",
        logger=None,
        dest_prefix=dest_prefix_for(source),
        mtp_manifest_dir=str(tmp_path / "logs"),
    )

    assert result["copied"] == 1
    assert touched[0][1].mtime == 1700000123
    assert touched[0][1].atime == 1700000100
    assert touched[0][1].birth == 1700000000


def test_mtp_to_local_pulls_and_sets_local_times(tmp_path: Path, monkeypatch):
    """Mocked MTP test: mtp -> local pull, then apply_times (write_local_times/utime)."""
    import filesync.copy as copy_mod

    dst = tmp_path / "b"
    dst.mkdir()

    def fake_pull(_adb, _serial, _remote, local):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(b"content")

    monkeypatch.setattr(copy_mod, "pull", fake_pull)
    monkeypatch.setattr(copy_mod, "list_remote_files", lambda *a, **k: ["f.bin"])
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: 7)
    monkeypatch.setattr(
        copy_mod,
        "read_android_times",
        lambda *a, **k: FileTimes(mtime=1700000123, atime=1700000100, birth=0),
    )

    source = Endpoint(kind="mtp", path="/sdcard/Src", device="SERIAL")
    dest = Endpoint(kind="local", path=str(dst))

    result = sync_directories(source, dest, adb="adb", logger=None)

    assert _without_elapsed(result) == _counts(copied=1, copied_bytes=7)
    copied = dst / "f.bin"
    assert copied.read_bytes() == b"content"
    assert read_local_times(str(copied)).mtime == 1700000123


def test_mtp_dest_persists_manifest_to_logs_dir_without_touching_source_manifest(
    tmp_path: Path, monkeypatch
):
    """dest.kind == mtp has nowhere on-device to keep hop metadata, so it
    must be persisted under a local logs/ manifest instead of being
    discarded -- and that must never overwrite the local source's own
    manifest (its recorded original times)."""
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    src.mkdir()
    (src / "f.bin").write_bytes(b"xyz")

    source_manifest = empty_manifest({"kind": "local"})
    upsert_file(source_manifest, "f.bin", FileRecord(size=3, mtime=1700000123, atime=1700000123, birth=0))
    save_manifest(str(src), source_manifest)
    source_manifest_bytes_before = (src / MANIFEST_NAME).read_bytes()

    monkeypatch.setattr(copy_mod, "push", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "ensure_remote_parent", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "remote_exists", lambda *a, **k: False)
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "write_android_times", lambda *a, **k: None)

    logs_dir = tmp_path / "logs"
    source = Endpoint(kind="local", path=str(src))
    dest = Endpoint(kind="mtp", path="/sdcard/Dest", device="SERIAL")

    result = sync_directories(source, dest, adb="adb", logger=None, mtp_manifest_dir=str(logs_dir))

    assert result["copied"] == 1
    dest_manifest = load_manifest(str(logs_dir))
    assert dest_manifest is not None
    assert dest_manifest.files["f.bin"].mtime == 1700000123

    assert (src / MANIFEST_NAME).read_bytes() == source_manifest_bytes_before


def test_dest_prefix_nests_files_and_manifest_keys(tmp_path: Path):
    src = tmp_path / "DCIM"
    dst = tmp_path / "backup"
    src.mkdir()
    dst.mkdir()
    photo = src / "Camera" / "pic.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"hello")

    result = sync_directories(
        Endpoint("local", str(src)),
        Endpoint("local", str(dst)),
        adb=None,
        logger=None,
        dest_prefix="DCIM",
    )
    copied = dst / "DCIM" / "Camera" / "pic.jpg"
    assert copied.read_bytes() == b"hello"
    assert result["copied"] == 1
    manifest = load_manifest(str(dst))
    assert manifest is not None
    assert "DCIM/Camera/pic.jpg" in manifest.files


def test_dest_prefix_for_wraps_folder_name_except_backup_and_sdcard(tmp_path: Path):
    from filesync.copy import dest_prefix_for
    from filesync.manifest import empty_manifest, save_manifest

    picsart = tmp_path / "Picsart"
    picsart.mkdir()
    assert dest_prefix_for(Endpoint("local", str(picsart))) == "Picsart"

    backup = tmp_path / "Phone Backup"
    backup.mkdir()
    save_manifest(str(backup), empty_manifest({"kind": "mtp"}))
    assert dest_prefix_for(Endpoint("local", str(backup))) == ""

    assert dest_prefix_for(Endpoint("mtp", "/sdcard/DCIM/", device="X")) == "DCIM"
    assert dest_prefix_for(Endpoint("mtp", "/sdcard/", device="X")) == ""
    assert dest_prefix_for(Endpoint("mtp", "/sdcard", device="X")) == ""

    deleted = tmp_path / "Phone Backup 2"
    deleted.mkdir()
    (deleted / "DCIM").mkdir()
    (deleted / "Pictures").mkdir()
    assert dest_prefix_for(Endpoint("local", str(deleted))) == ""

    only_dcim = tmp_path / "DCIM"
    only_dcim.mkdir()
    (only_dcim / "Camera").mkdir()
    assert dest_prefix_for(Endpoint("local", str(only_dcim))) == "DCIM"


def test_mtp_dest_mkdir_parent_before_push(tmp_path: Path, monkeypatch):
    import filesync.copy as copy_mod

    src = tmp_path / "DCIM"
    src.mkdir()
    (src / "Camera").mkdir()
    (src / "Camera" / "pic.jpg").write_bytes(b"xyz")

    parents = []
    monkeypatch.setattr(copy_mod, "push", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "ensure_remote_parent", lambda adb, serial, remote: parents.append(remote))
    monkeypatch.setattr(copy_mod, "remote_exists", lambda *a, **k: False)
    monkeypatch.setattr(copy_mod, "remote_size", lambda *a, **k: None)
    monkeypatch.setattr(copy_mod, "write_android_times", lambda *a, **k: None)

    sync_directories(
        Endpoint("local", str(src)),
        Endpoint("mtp", "/sdcard/", device="SERIAL"),
        adb="adb",
        logger=None,
        dest_prefix="DCIM",
        mtp_manifest_dir=str(tmp_path / "logs"),
    )
    assert parents == ["/sdcard/DCIM/Camera/pic.jpg"]


def test_ignore_prefixes_skips_those_files(tmp_path: Path):
    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "keep").mkdir()
    (src / "skip").mkdir()
    (src / "keep" / "ok.txt").write_bytes(b"ok")
    (src / "skip" / "no.txt").write_bytes(b"no")
    (src / "skip" / "nested").mkdir()
    (src / "skip" / "nested" / "deep.txt").write_bytes(b"deep")

    result = sync_directories(
        Endpoint("local", str(src)),
        Endpoint("local", str(dst)),
        adb=None,
        logger=None,
        ignore_prefixes=["skip"],
    )
    assert _without_elapsed(result) == _counts(copied=1, ignored=2, copied_bytes=2)
    assert (dst / "keep" / "ok.txt").exists()
    assert not (dst / "skip" / "no.txt").exists()
    assert not (dst / "skip" / "nested" / "deep.txt").exists()


def test_manifest_lock_does_not_abort_copy(tmp_path: Path, monkeypatch):
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "f.bin").write_bytes(b"xyz")

    def boom(*_args, **_kwargs):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(copy_mod, "save_manifest", boom)
    result = sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)
    assert result["copied"] == 1
    assert (dst / "f.bin").read_bytes() == b"xyz"


def test_keyboard_interrupt_returns_partial_summary(tmp_path: Path, monkeypatch):
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "one.bin").write_bytes(b"aaa")
    (src / "two.bin").write_bytes(b"bbb")
    real_copy = copy_mod.copy_bytes
    seen = {"n": 0}

    def flaky(source, dest, relpath, adb, dest_relpath=None):
        seen["n"] += 1
        if seen["n"] >= 2:
            raise KeyboardInterrupt
        return real_copy(source, dest, relpath, adb, dest_relpath=dest_relpath)

    monkeypatch.setattr(copy_mod, "copy_bytes", flaky)
    result = sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)
    assert result["stopped"] is True
    assert result["copied"] == 1
    assert result["copied_bytes"] == 3
    assert (dst / "one.bin").exists()
    assert not (dst / "two.bin").exists()


def test_unexpected_error_returns_partial_summary(tmp_path: Path, monkeypatch):
    import filesync.copy as copy_mod

    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    (src / "one.bin").write_bytes(b"aaa")
    (src / "two.bin").write_bytes(b"bbb")
    real = copy_mod.dest_size
    seen = {"n": 0}

    def flaky(*args, **kwargs):
        seen["n"] += 1
        if seen["n"] >= 2:
            raise RuntimeError("disk vanished")
        return real(*args, **kwargs)

    monkeypatch.setattr(copy_mod, "dest_size", flaky)
    result = sync_directories(Endpoint("local", str(src)), Endpoint("local", str(dst)), None, None)
    assert result["copied"] == 1
    assert result["error"] == "disk vanished"
    assert (dst / "one.bin").exists()


def test_source_work_bytes_subtracts_ignored(tmp_path: Path):
    from filesync.copy import source_work_bytes

    src = tmp_path / "a"
    (src / "keep").mkdir(parents=True)
    (src / "skip").mkdir()
    (src / "keep" / "ok.txt").write_bytes(b"ok")
    (src / "skip" / "no.txt").write_bytes(b"no")
    total = source_work_bytes(Endpoint("local", str(src)), None, ignore_prefixes=["skip"])
    assert total == 2


def test_source_job_stats_counts_files_and_bytes(tmp_path: Path):
    from filesync.copy import source_job_stats

    src = tmp_path / "a"
    (src / "keep").mkdir(parents=True)
    (src / "skip").mkdir()
    (src / "keep" / "ok.txt").write_bytes(b"ok")
    (src / "skip" / "no.txt").write_bytes(b"nope")
    stats = source_job_stats(Endpoint("local", str(src)), None, ignore_prefixes=["skip"])
    assert stats["files"] == 1
    assert stats["ignored"] == 1
    assert stats["bytes"] == 2
    assert stats["copy_bytes"] == 2
    assert stats["already_bytes"] == 0
    assert stats["relpaths"] == ["keep/ok.txt"]


def test_source_job_stats_subtracts_files_already_on_dest(tmp_path: Path):
    from filesync.copy import source_job_stats

    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "Camera").mkdir(parents=True)
    (dst / "Camera").mkdir(parents=True)
    (src / "Camera" / "old.jpg").write_bytes(b"12345")
    (src / "Camera" / "new.jpg").write_bytes(b"ab")
    (dst / "Camera" / "old.jpg").write_bytes(b"12345")
    stats = source_job_stats(
        Endpoint("local", str(src)),
        None,
        dest=Endpoint("local", str(dst)),
        dest_prefix="",
    )
    assert stats["files"] == 2
    assert stats["already_files"] == 1
    assert stats["already_bytes"] == 5
    assert stats["copy_files"] == 1
    assert stats["copy_bytes"] == 2
    assert stats["copy_relpaths"] == ["Camera/new.jpg"]
    assert stats["copy_relpaths"] == ["Camera/new.jpg"]


def test_source_job_stats_matches_wrapped_dest_prefix(tmp_path: Path):
    from filesync.copy import source_job_stats

    src = tmp_path / "Camera"
    dst = tmp_path / "backup"
    src.mkdir()
    (dst / "Camera").mkdir(parents=True)
    (src / "old.jpg").write_bytes(b"12345")
    (src / "new.jpg").write_bytes(b"ab")
    (dst / "Camera" / "old.jpg").write_bytes(b"12345")
    stats = source_job_stats(
        Endpoint("local", str(src)),
        None,
        dest=Endpoint("local", str(dst)),
        dest_prefix="Camera",
    )
    assert stats["already_files"] == 1
    assert stats["already_bytes"] == 5
    assert stats["copy_bytes"] == 2
    assert stats["copy_relpaths"] == ["new.jpg"]


def test_planned_sync_only_visits_files_not_already_on_dest(tmp_path: Path, monkeypatch):
    import filesync.copy as copy_mod
    from filesync.copy import source_job_stats

    src = tmp_path / "Camera"
    dst = tmp_path / "backup"
    src.mkdir()
    (dst / "Camera").mkdir(parents=True)
    (src / "old.jpg").write_bytes(b"12345")
    (src / "new.jpg").write_bytes(b"ab")
    (dst / "Camera" / "old.jpg").write_bytes(b"12345")
    stats = source_job_stats(
        Endpoint("local", str(src)),
        None,
        dest=Endpoint("local", str(dst)),
        dest_prefix="Camera",
    )
    visited: list[str] = []
    real_capture = copy_mod.capture_record

    def tracking(source, relpath, adb):
        visited.append(relpath)
        return real_capture(source, relpath, adb)

    monkeypatch.setattr(copy_mod, "capture_record", tracking)
    result = sync_directories(
        Endpoint("local", str(src)),
        Endpoint("local", str(dst)),
        adb=None,
        logger=None,
        dest_prefix="Camera",
        planned=stats,
    )
    assert visited == ["new.jpg"]
    assert result["copied"] == 1
    assert result["skipped"] == 1
    assert result["copied_bytes"] == 2
    assert result["skipped_bytes"] == 5

