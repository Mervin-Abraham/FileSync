from __future__ import annotations

import logging
import os
import posixpath
import shutil
import tempfile
import time
from dataclasses import dataclass, replace

from filesync.adb import ensure_remote_parent, list_remote_files, pull, push, remote_exists, remote_size, remote_tree_bytes
from filesync.manifest import (
    MANIFEST_NAME,
    FileRecord,
    Manifest,
    empty_manifest,
    load_manifest,
    record_for,
    save_manifest,
    upsert_file,
)
from filesync.paths import folder_basename, is_ignored, join_relpath, normalize_relpath
from filesync.sizes import local_tree_size
from filesync.times import (
    FileTimes,
    read_android_times,
    read_local_times,
    write_android_times,
    write_local_times,
)
from filesync.ui import error as ui_error, sync_progress, warn as ui_warn


@dataclass
class Endpoint:
    kind: str
    path: str
    device: str | None = None


def same_size(dest_size: int | None, source_size: int) -> bool:
    return dest_size is not None and dest_size == source_size


def _local_path(endpoint: Endpoint, relpath: str) -> str:
    return os.path.join(endpoint.path, *relpath.split("/"))


def _remote_path(root: str, relpath: str) -> str:
    return posixpath.join(root.rstrip("/") or "/", relpath)


def list_source_files(source: Endpoint, adb: str | None) -> list[str]:
    if source.kind == "local":
        files = []
        for dirpath, _dirnames, filenames in os.walk(source.path):
            for filename in filenames:
                if filename == MANIFEST_NAME:
                    continue
                full_path = os.path.join(dirpath, filename)
                files.append(normalize_relpath(full_path, root=source.path))
        return sorted(files)
    return list_remote_files(adb, source.device, source.path)


def source_size(source: Endpoint, relpath: str, adb: str | None) -> int:
    if source.kind == "local":
        return os.path.getsize(_local_path(source, relpath))
    remote = _remote_path(source.path, relpath)
    size = remote_size(adb, source.device, remote)
    return size if size is not None else 0


def dest_size(dest: Endpoint, relpath: str, adb: str | None) -> int | None:
    if dest.kind == "local":
        local_path = _local_path(dest, relpath)
        if not os.path.exists(local_path):
            return None
        return os.path.getsize(local_path)
    remote = _remote_path(dest.path, relpath)
    if not remote_exists(adb, dest.device, remote):
        return None
    return remote_size(adb, dest.device, remote)


def capture_record(source: Endpoint, relpath: str, adb: str | None) -> FileRecord:
    """Capture size/times for a source file.

    Missing Android timestamps no longer abort the copy. Bytes still
    transfer; `times_known=False` so we do not stamp 1970 or write fake
    times into the dest manifest.
    """
    size = source_size(source, relpath, adb)
    if source.kind == "local":
        times = read_local_times(_local_path(source, relpath))
        return FileRecord(size=size, mtime=times.mtime, atime=times.atime, birth=times.birth)
    remote = _remote_path(source.path, relpath)
    times = read_android_times(adb, source.device, remote)
    if times is None:
        return FileRecord(size=size, mtime=0, atime=0, birth=0, times_known=False)
    return FileRecord(size=size, mtime=times.mtime, atime=times.atime, birth=times.birth)


PHONE_BACKUP_ROOT_DIRS = frozenset(
    {
        "DCIM",
        "Pictures",
        "Download",
        "Downloads",
        "Documents",
        "Movies",
        "Music",
        "Recordings",
        "Notifications",
        "Ringtones",
        "Alarms",
        "Podcasts",
        "Audiobooks",
    }
)


def looks_like_phone_backup_root(path: str) -> bool:
    """True when this PC folder looks like hop-1 output (DCIM, Pictures, …)."""
    try:
        names = os.listdir(path)
    except OSError:
        return False
    for name in names:
        if name not in PHONE_BACKUP_ROOT_DIRS:
            continue
        if os.path.isdir(os.path.join(path, name)):
            return True
    return False


def dest_prefix_for(source: Endpoint) -> str:
    """Folder name to nest under dest, or empty when wrapping would break hop 2 / phone root."""
    if source.kind == "local" and (
        load_manifest(source.path) is not None or looks_like_phone_backup_root(source.path)
    ):
        return ""
    name = folder_basename(source.path)
    if source.kind == "mtp" and name in ("", "sdcard"):
        return ""
    return name


def copy_bytes(
    source: Endpoint,
    dest: Endpoint,
    relpath: str,
    adb: str | None,
    dest_relpath: str | None = None,
) -> None:
    dest_relpath = relpath if dest_relpath is None else dest_relpath
    if source.kind == "local" and dest.kind == "local":
        src_path = _local_path(source, relpath)
        dst_path = _local_path(dest, dest_relpath)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
    elif source.kind == "local" and dest.kind == "mtp":
        remote = _remote_path(dest.path, dest_relpath)
        ensure_remote_parent(adb, dest.device, remote)
        push(adb, dest.device, _local_path(source, relpath), remote)
    elif source.kind == "mtp" and dest.kind == "local":
        dst_path = _local_path(dest, dest_relpath)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        pull(adb, source.device, _remote_path(source.path, relpath), dst_path)
    else:
        remote_dst = _remote_path(dest.path, dest_relpath)
        ensure_remote_parent(adb, dest.device, remote_dst)
        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            pull(adb, source.device, _remote_path(source.path, relpath), tmp_path)
            push(adb, dest.device, tmp_path, remote_dst)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def apply_times(dest: Endpoint, relpath: str, record: FileRecord, adb: str | None) -> None:
    times = FileTimes(mtime=record.mtime, atime=record.atime, birth=record.birth)
    if dest.kind == "local":
        write_local_times(_local_path(dest, relpath), times)
    else:
        remote = _remote_path(dest.path, relpath)
        write_android_times(adb, dest.device, remote, times)


def _same_endpoint(source: Endpoint, dest: Endpoint) -> bool:
    if source.kind == "local" and dest.kind == "local":
        return os.path.abspath(source.path) == os.path.abspath(dest.path)
    if source.kind == "mtp" and dest.kind == "mtp":
        return source.device == dest.device and normalize_relpath(source.path) == normalize_relpath(dest.path)
    return False


MTP_MANIFEST_DIR = "logs"


def source_work_bytes(
    source: Endpoint,
    adb: str | None,
    ignore_prefixes: list[str] | tuple[str, ...] = (),
) -> int:
    """Best-effort total bytes to consider (source tree minus skipped folders)."""
    try:
        total = _endpoint_tree_bytes(source, "", adb)
        for prefix in ignore_prefixes:
            total -= _endpoint_tree_bytes(source, prefix, adb)
        return max(0, total)
    except OSError:
        return 0


def _endpoint_tree_bytes(source: Endpoint, rel: str, adb: str | None) -> int:
    if source.kind == "local":
        path = _local_path(source, rel) if rel else source.path
        return local_tree_size(path)
    if not adb or not source.device:
        return 0
    remote = source.path if not rel else _remote_path(source.path, rel)
    return remote_tree_bytes(adb, source.device, remote) or 0


def dest_matching_bytes(
    dest: Endpoint,
    dest_prefix: str,
    source_relpaths: list[str] | set[str],
    adb: str | None,
) -> tuple[int, int, set[str]]:
    """Source relpaths that already exist under dest (by relative path)."""
    wanted = set(source_relpaths)
    if not wanted:
        return 0, 0, set()
    if dest.kind == "local":
        root = os.path.join(dest.path, dest_prefix) if dest_prefix else dest.path
        if not os.path.isdir(root):
            return 0, 0, set()
        found: set[str] = set()
        nbytes = 0
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if filename == MANIFEST_NAME:
                    continue
                full = os.path.join(dirpath, filename)
                rel = normalize_relpath(full, root=root)
                if rel not in wanted:
                    continue
                found.add(rel)
                try:
                    nbytes += os.path.getsize(full)
                except OSError:
                    continue
        return len(found), nbytes, found
    if not adb or not dest.device:
        return 0, 0, set()
    remote = dest.path if not dest_prefix else _remote_path(dest.path, dest_prefix)
    nbytes = remote_tree_bytes(adb, dest.device, remote) or 0
    return 0, nbytes, set()


def source_job_stats(
    source: Endpoint,
    adb: str | None,
    ignore_prefixes: list[str] | tuple[str, ...] = (),
    dest: Endpoint | None = None,
    dest_prefix: str = "",
) -> dict:
    """Files and bytes that will be considered, before copy starts."""
    relpaths = list_source_files(source, adb)
    ignored = 0
    kept_paths: list[str] = []
    for relpath in relpaths:
        if is_ignored(relpath, ignore_prefixes):
            ignored += 1
        else:
            kept_paths.append(relpath)
    nbytes = source_work_bytes(source, adb, ignore_prefixes)
    already_files = 0
    already_bytes = 0
    already_relpaths: set[str] = set()
    if dest is not None:
        already_files, already_bytes, already_relpaths = dest_matching_bytes(
            dest, dest_prefix, kept_paths, adb
        )
        already_bytes = min(already_bytes, nbytes)
        already_files = min(already_files, len(kept_paths))
    copy_relpaths = [path for path in kept_paths if path not in already_relpaths]
    return {
        "files": len(kept_paths),
        "ignored": ignored,
        "bytes": nbytes,
        "already_files": already_files,
        "already_bytes": already_bytes,
        "copy_files": len(copy_relpaths),
        "copy_bytes": max(0, nbytes - already_bytes),
        "relpaths": kept_paths,
        "copy_relpaths": copy_relpaths,
    }


def sync_directories(
    source: Endpoint,
    dest: Endpoint,
    adb: str | None,
    logger,
    mtp_manifest_dir: str = MTP_MANIFEST_DIR,
    dest_prefix: str = "",
    ignore_prefixes: list[str] | tuple[str, ...] = (),
    planned: dict | None = None,
) -> dict:
    if logger is None:
        logger = logging.getLogger("filesync")

    if _same_endpoint(source, dest):
        raise ValueError("Source and destination are the same")

    planned = planned or {}
    pre_skipped = 0
    pre_skipped_bytes = 0
    if planned.get("copy_relpaths") is not None:
        relpaths = list(planned["copy_relpaths"])
        ignored_count = int(planned.get("ignored") or 0)
        pre_skipped = int(planned.get("already_files") or 0)
        pre_skipped_bytes = int(planned.get("already_bytes") or 0)
    elif planned.get("relpaths") is not None:
        relpaths = list(planned["relpaths"])
        ignored_count = int(planned.get("ignored") or 0)
    else:
        relpaths = list_source_files(source, adb)
        ignored_count = 0
        if ignore_prefixes:
            kept = []
            for relpath in relpaths:
                if is_ignored(relpath, ignore_prefixes):
                    ignored_count += 1
                else:
                    kept.append(relpath)
            relpaths = kept

    source_manifest: Manifest | None = load_manifest(source.path) if source.kind == "local" else None

    if dest.kind == "local":
        dest_manifest = load_manifest(dest.path) or empty_manifest(
            {"kind": source.kind, "path": source.path, "device": source.device}
        )
    else:
        dest_manifest = empty_manifest({"kind": source.kind, "path": source.path, "device": source.device})

    persist_every = 25
    dirty = 0

    def _persist_dest_manifest(force: bool = False) -> None:
        nonlocal dirty
        if not force and dirty < persist_every:
            return
        try:
            if dest.kind == "local":
                save_manifest(dest.path, dest_manifest)
            else:
                os.makedirs(mtp_manifest_dir, exist_ok=True)
                save_manifest(mtp_manifest_dir, dest_manifest)
            dirty = 0
        except OSError as exc:
            logger.exception("Failed to save manifest")
            if force:
                ui_warn(f"Could not save backup log: {exc}")

    counts = {
        "copied": 0,
        "skipped": pre_skipped,
        "failed": 0,
        "ignored": ignored_count,
        "copied_bytes": 0,
        "skipped_bytes": pre_skipped_bytes,
        "failed_bytes": 0,
        "stopped": False,
        "error": "",
        "elapsed_seconds": 0.0,
    }

    def _first_error(relpath: str, message: str) -> None:
        if counts["failed"] == 0:
            ui_error(f"First error ({relpath}): {message}")

    total_bytes = int(planned["bytes"]) if planned.get("bytes") is not None else source_work_bytes(source, adb, ignore_prefixes)
    bytes_to_copy = planned.get("copy_bytes")
    if bytes_to_copy is None:
        bytes_to_copy = total_bytes
    started = time.perf_counter()

    with sync_progress(relpaths, total_bytes=total_bytes, copy_bytes=int(bytes_to_copy or 0)) as progress:
        try:
            for relpath in progress:
                try:
                    captured = capture_record(source, relpath, adb)
                except Exception as exc:
                    logger.exception("Failed to capture record for %s", relpath)
                    _first_error(relpath, str(exc))
                    counts["failed"] += 1
                    progress.record_fail(0)
                    continue

                progress.update_file(relpath, captured.size)
                record = record_for(relpath, source_manifest, captured)
                dest_relpath = join_relpath(dest_prefix, relpath)

                if same_size(dest_size(dest, dest_relpath, adb), record.size):
                    if record.times_known:
                        try:
                            apply_times(dest, dest_relpath, record, adb)
                        except Exception:
                            logger.exception("Failed to set times on %s", relpath)
                            _first_error(relpath, "could not set timestamps")
                        upsert_file(dest_manifest, dest_relpath, record)
                        dirty += 1
                        _persist_dest_manifest()
                    counts["skipped"] += 1
                    counts["skipped_bytes"] += record.size
                    progress.record_skip(record.size)
                    continue

                copy_started = time.perf_counter()
                try:
                    copy_bytes(source, dest, relpath, adb, dest_relpath=dest_relpath)
                except KeyboardInterrupt:
                    if dest.kind == "local":
                        dest_file = _local_path(dest, dest_relpath)
                        if os.path.exists(dest_file):
                            os.remove(dest_file)
                    raise
                except Exception as exc:
                    logger.exception("Failed to copy %s", relpath)
                    _first_error(relpath, str(exc))
                    counts["failed"] += 1
                    counts["failed_bytes"] += record.size
                    if dest.kind == "local":
                        dest_file = _local_path(dest, dest_relpath)
                        if os.path.exists(dest_file):
                            os.remove(dest_file)
                    progress.record_fail(record.size)
                    continue

                elapsed = time.perf_counter() - copy_started
                if dest.kind == "local":
                    dest_file = _local_path(dest, dest_relpath)
                    if os.path.isfile(dest_file):
                        record = replace(record, size=os.path.getsize(dest_file))

                if record.times_known:
                    try:
                        apply_times(dest, dest_relpath, record, adb)
                    except Exception:
                        logger.exception("Failed to set times on %s after copy", relpath)
                    upsert_file(dest_manifest, dest_relpath, record)
                    dirty += 1
                    _persist_dest_manifest()
                counts["copied"] += 1
                counts["copied_bytes"] += record.size
                progress.record_copy(relpath, record.size, elapsed)
        except KeyboardInterrupt:
            counts["stopped"] = True
            ui_warn("Stopped.")
        except Exception as exc:
            counts["error"] = str(exc)
            logger.exception("Error during sync")
            ui_error(f"Error during sync: {exc}")
        finally:
            _persist_dest_manifest(force=True)

    counts["elapsed_seconds"] = time.perf_counter() - started
    return counts
