import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from filesync.times import (
    FileTimes,
    android_touch_args,
    android_touch_t_format,
    parse_stat_output,
    read_android_times,
    read_local_times,
    write_android_times,
    write_local_times,
)


def test_parse_stat_output():
    times = parse_stat_output("1700000123 1700000100 0\n")
    assert times.mtime == 1700000123
    assert times.atime == 1700000100
    assert times.birth == 0
    assert times.effective_birth() == 1700000123


def test_parse_stat_rejects_garbage():
    with pytest.raises(ValueError):
        parse_stat_output("not-a-stat")


def test_parse_stat_output_accepts_mtime_only():
    times = parse_stat_output("1700000123\n")
    assert times.mtime == 1700000123
    assert times.atime == 1700000123
    assert times.birth == 0


def test_parse_stat_output_ignores_non_numeric_birth():
    times = parse_stat_output("1700000123 1700000100 %W\n")
    assert times.mtime == 1700000123
    assert times.atime == 1700000100
    assert times.birth == 0


def test_write_and_read_local_mtime(tmp_path: Path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"abc")
    times = FileTimes(mtime=1700000123, atime=1700000123, birth=0)
    write_local_times(str(path), times)
    read = read_local_times(str(path))
    assert read.mtime == 1700000123


def test_touch_t_format():
    assert android_touch_t_format(1700000123) == "202311142215.23"


def test_android_touch_args():
    times = FileTimes(mtime=1700000123, atime=1700000100, birth=0)
    assert android_touch_args(times) == ["-m", "-d", "@1700000123"]


@patch("filesync.times.run_shell")
def test_write_android_times_first_call_succeeds(mock_run_shell):
    mock_run_shell.return_value = MagicMock(returncode=0)
    times = FileTimes(mtime=1700000123, atime=1700000100, birth=0)

    write_android_times("adb", "serial", "/sdcard/photo.jpg", times)

    mock_run_shell.assert_called_once_with(
        "adb",
        "serial",
        ["sh", "-c", "touch -m -d @1700000123 /sdcard/photo.jpg"],
    )


@patch("filesync.times.run_shell")
def test_write_android_times_falls_back_to_t_format(mock_run_shell):
    mock_run_shell.side_effect = [
        MagicMock(returncode=1),
        MagicMock(returncode=0),
    ]
    times = FileTimes(mtime=1700000123, atime=1700000100, birth=0)

    write_android_times("adb", "serial", "/sdcard/photo.jpg", times)

    assert mock_run_shell.call_count == 2
    mock_run_shell.assert_any_call(
        "adb",
        "serial",
        ["sh", "-c", "touch -m -d @1700000123 /sdcard/photo.jpg"],
    )
    mock_run_shell.assert_any_call(
        "adb",
        "serial",
        ["sh", "-c", "touch -m -t 202311142215.23 /sdcard/photo.jpg"],
    )


@patch("filesync.times.run_shell")
def test_write_android_times_raises_when_both_attempts_fail(mock_run_shell):
    mock_run_shell.side_effect = [
        MagicMock(returncode=1),
        MagicMock(returncode=1),
    ]
    times = FileTimes(mtime=1700000123, atime=1700000100, birth=0)

    with pytest.raises(RuntimeError):
        write_android_times("adb", "serial", "/sdcard/photo.jpg", times)

    assert mock_run_shell.call_count == 2


@patch("filesync.times.run_shell")
def test_write_android_times_quotes_spaced_remote_path(mock_run_shell):
    mock_run_shell.return_value = MagicMock(returncode=0)
    times = FileTimes(mtime=1700000123, atime=1700000100, birth=0)

    write_android_times("adb", "serial", "/sdcard/DCIM/My Photo.jpg", times)

    args = mock_run_shell.call_args[0][2]
    assert args[:2] == ["sh", "-c"]
    assert "'/sdcard/DCIM/My Photo.jpg'" in args[2]


@patch("filesync.times.run_shell")
def test_read_android_times_quotes_spaced_remote_path(mock_run_shell):
    mock_run_shell.return_value = MagicMock(returncode=0, stdout="1700000123 1700000100 0\n")

    read_android_times("adb", "serial", "/sdcard/DCIM/My Photo.jpg")

    args = mock_run_shell.call_args[0][2]
    assert args[:2] == ["sh", "-c"]
    assert "'/sdcard/DCIM/My Photo.jpg'" in args[2]


@patch("filesync.times.run_shell")
def test_read_android_times_falls_back_when_first_stat_fails(mock_run_shell):
    mock_run_shell.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="bad format"),
        MagicMock(returncode=0, stdout="1700000123\n", stderr=""),
    ]
    times = read_android_times("adb", "serial", "/sdcard/a.jpg")
    assert times is not None
    assert times.mtime == 1700000123
    assert mock_run_shell.call_count == 2
    first_cmd = mock_run_shell.call_args_list[0][0][2][2]
    assert first_cmd.startswith("stat -c")
    assert "--" not in first_cmd.split()
    second_cmd = mock_run_shell.call_args_list[1][0][2][2]
    assert "toybox" in second_cmd


def test_write_local_times_windows_sets_creation_time_to_mtime_when_birth_zero(monkeypatch):
    """Exercise the win32 branch of write_local_times without a real
    Windows machine or the pywin32 package installed, by injecting fake
    win32file/pywintypes modules and forcing sys.platform to 'win32'."""
    fake_win32file = MagicMock()
    fake_win32file.GENERIC_WRITE = "GENERIC_WRITE"
    fake_win32file.OPEN_EXISTING = "OPEN_EXISTING"
    fake_handle = MagicMock(name="handle")
    fake_win32file.CreateFile.return_value = fake_handle

    fake_pywintypes = types.SimpleNamespace(Time=lambda epoch: ("PYWINTIME", epoch))

    monkeypatch.setitem(sys.modules, "win32file", fake_win32file)
    monkeypatch.setitem(sys.modules, "pywintypes", fake_pywintypes)
    monkeypatch.setattr(sys, "platform", "win32")

    times = FileTimes(mtime=1700000123, atime=1700000100, birth=0)
    write_local_times(r"C:\fake\photo.jpg", times)

    fake_win32file.CreateFile.assert_called_once_with(
        r"C:\fake\photo.jpg",
        fake_win32file.GENERIC_WRITE,
        0,
        None,
        fake_win32file.OPEN_EXISTING,
        0,
        0,
    )
    fake_win32file.SetFileTime.assert_called_once_with(
        fake_handle,
        CreationTime=("PYWINTIME", 1700000123),
        LastAccessTime=("PYWINTIME", 1700000100),
        LastWriteTime=("PYWINTIME", 1700000123),
    )
    fake_win32file.CloseHandle.assert_called_once_with(fake_handle)
