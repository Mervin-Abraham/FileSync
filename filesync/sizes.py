"""Human-readable sizes, rates, and local folder totals."""

from __future__ import annotations

import os
from collections import deque
from math import ceil


def format_size(nbytes: int | float | None) -> str:
    """1024-based size for display, e.g. 2487219 → '2.4 MB'."""
    if nbytes is None:
        return "?"
    remaining = float(max(0, int(nbytes)))
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    index = 0
    while remaining >= 1024 and index < len(units) - 1:
        remaining /= 1024
        index += 1
    if index == 0:
        return f"{int(remaining)} B"
    if remaining >= 10:
        return f"{remaining:.0f} {units[index]}"
    return f"{remaining:.1f} {units[index]}"


def local_tree_size(path: str) -> int:
    total = 0
    if not os.path.isdir(path):
        if os.path.isfile(path):
            try:
                return os.path.getsize(path)
            except OSError:
                return 0
        return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            try:
                total += os.path.getsize(full)
            except OSError:
                continue
    return total


def parse_du_sk(output: str) -> dict[str, int]:
    """Parse `du -sk` lines into {posix_path: bytes}."""
    sizes: dict[str, int] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        path = parts[1].strip().rstrip("/")
        if path:
            sizes[path] = int(parts[0]) * 1024
    return sizes


def format_duration(seconds: float | None) -> str:
    """Per-file elapsed time: 0.07s, 12.3s, 1:05, 1:17:00."""
    if seconds is None:
        return "--"
    if seconds < 0:
        seconds = 0.0
    if seconds < 60:
        if seconds < 10:
            return f"{seconds:.2f}s"
        return f"{seconds:.1f}s"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_speed(bps: float) -> str:
    if bps <= 0:
        return "—"
    return f"{format_size(int(bps))}/s"


def format_eta(seconds: float | None) -> str:
    """Remaining time as M:SS or H:MM:SS, or -- if unknown."""
    if seconds is None or seconds < 0:
        return "--"
    total = int(ceil(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def eta_seconds(remaining_bytes: int, bytes_per_second: float) -> float | None:
    if remaining_bytes <= 0:
        return 0.0
    if bytes_per_second <= 0:
        return None
    return remaining_bytes / bytes_per_second


class ThroughputWindow:
    """Last N completed copies. Speed = sum(bytes) / sum(seconds).

    Matches rsync's short sliding window, sampled per file because ADB
    pull/push only report size after the whole file finishes.
    """

    def __init__(self, maxlen: int = 5):
        self._samples: deque[tuple[int, float]] = deque(maxlen=maxlen)
        self._all_bytes = 0
        self._all_seconds = 0.0

    def add(self, nbytes: int, seconds: float) -> None:
        if nbytes > 0 and seconds > 0:
            self._samples.append((nbytes, seconds))
            self._all_bytes += nbytes
            self._all_seconds += seconds

    def bytes_per_second(self) -> float:
        """Recent window — shown as live speed."""
        if not self._samples:
            return 0.0
        total_bytes = sum(item[0] for item in self._samples)
        total_time = sum(item[1] for item in self._samples)
        if total_time <= 0:
            return 0.0
        return total_bytes / total_time

    def overall_bytes_per_second(self) -> float:
        """All copies this run — used for ETA so early skips don't inflate it."""
        if self._all_seconds <= 0:
            return 0.0
        return self._all_bytes / self._all_seconds


def display_path(relpath: str, max_len: int = 72) -> str:
    """Keep folder + filename. If too long, ellipsis the middle of the name."""
    path = (relpath or "").replace("\\", "/")
    if max_len < 8 or len(path) <= max_len:
        return path
    folder = ""
    name = path
    if "/" in path:
        folder, name = path.rsplit("/", 1)
    prefix = f"{folder}/" if folder else ""
    if len(prefix) >= max_len - 6:
        keep_dir = max_len - len(name) - 2
        if keep_dir >= 4:
            return prefix[: keep_dir - 1] + "…/" + name
        return "…" + path[-(max_len - 1) :]
    budget = max_len - len(prefix)
    if len(name) <= budget:
        return prefix + name
    ext = ""
    stem = name
    if "." in name and not name.startswith("."):
        stem, ext = name.rsplit(".", 1)
        ext = "." + ext
    inner = max(3, budget - len(ext) - 1)
    if len(stem) <= inner:
        return prefix + name[: budget - 1] + "…"
    head = max(1, inner // 2)
    tail = max(1, inner - head)
    return prefix + stem[:head] + "…" + stem[-tail:] + ext
