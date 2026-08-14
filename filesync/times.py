from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from filesync.adb import build_shell_command, run_shell


@dataclass
class FileTimes:
    mtime: int
    atime: int
    birth: int

    def effective_birth(self) -> int:
        return self.birth if self.birth else self.mtime


def parse_stat_output(output: str) -> FileTimes:
    tokens = (output or "").strip().split()
    nums: list[int] = []
    for token in tokens:
        try:
            nums.append(int(token))
        except ValueError:
            if nums:
                break
    if not nums:
        raise ValueError(f"Unexpected stat output: {output!r}")
    mtime = nums[0]
    atime = nums[1] if len(nums) > 1 else mtime
    birth = nums[2] if len(nums) > 2 else 0
    if birth < 0:
        birth = 0
    return FileTimes(mtime=mtime, atime=atime, birth=birth)


def android_touch_t_format(mtime: int) -> str:
    stamp = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return stamp.strftime("%Y%m%d%H%M.%S")


def android_touch_args(times: FileTimes) -> list[str]:
    return ["-m", "-d", f"@{times.mtime}"]


def read_local_times(path: str) -> FileTimes:
    if sys.platform == "win32":
        import pywintypes
        import win32file

        handle = win32file.CreateFile(
            path,
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            None,
            win32file.OPEN_EXISTING,
            0,
            0,
        )
        try:
            ctime, atime, mtime = win32file.GetFileTime(handle)
            return FileTimes(
                mtime=int(mtime.timestamp()),
                atime=int(atime.timestamp()),
                birth=int(ctime.timestamp()),
            )
        finally:
            win32file.CloseHandle(handle)
    stat = os.stat(path)
    birth = int(getattr(stat, "st_birthtime", 0) or 0)
    return FileTimes(mtime=int(stat.st_mtime), atime=int(stat.st_atime), birth=birth)


def write_local_times(path: str, times: FileTimes) -> None:
    atime = times.atime or times.mtime
    if sys.platform == "win32":
        import pywintypes
        import win32file

        stamp_mtime = pywintypes.Time(times.mtime)
        stamp_atime = pywintypes.Time(atime)
        stamp_birth = pywintypes.Time(times.effective_birth())
        handle = win32file.CreateFile(
            path,
            win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,
            0,
        )
        try:
            win32file.SetFileTime(
                handle,
                CreationTime=stamp_birth,
                LastAccessTime=stamp_atime,
                LastWriteTime=stamp_mtime,
            )
        finally:
            win32file.CloseHandle(handle)
        return
    os.utime(path, (atime, times.mtime))


_STAT_FORMATS = ("%Y", "%Y %X", "%Y %X %Z", "%Y %X %W")


def read_android_times(adb: str, serial: str, remote: str) -> FileTimes | None:
    """Read mtime from the phone. Prefer simple `%Y`; GNU `%W` often fails."""
    commands: list[tuple[str, ...]] = []
    for fmt in _STAT_FORMATS:
        commands.append(("stat", "-c", fmt, remote))
        commands.append(("toybox", "stat", "-c", fmt, remote))
    commands.append(("date", "-r", remote, "+%s"))
    for parts in commands:
        result = run_shell(adb, serial, build_shell_command(*parts))
        try:
            return parse_stat_output(result.stdout)
        except ValueError:
            continue
    return None


def write_android_times(adb: str, serial: str, remote: str, times: FileTimes) -> None:
    """Set mtime (and best-effort atime) on a remote file.

    Tries `touch -d @<epoch>` first, then falls back to `touch -t
    <YYYYmmddHHMM.SS>` for toybox/busybox `touch` builds that don't support
    `-d`. Raises if both attempts fail so callers can't mistake a silent
    no-op for success.
    """
    first = run_shell(adb, serial, build_shell_command("touch", *android_touch_args(times), remote))
    if first.returncode == 0:
        return
    second = run_shell(
        adb, serial, build_shell_command("touch", "-m", "-t", android_touch_t_format(times.mtime), remote)
    )
    if second.returncode != 0:
        raise RuntimeError(
            f"Failed to set times on {remote!r}: "
            f"'touch -d' exited {first.returncode}, 'touch -t' fallback exited {second.returncode}"
        )
