import shlex
from unittest.mock import MagicMock, patch

import pytest

from filesync.adb import (
    DEFAULT_ADB_PATH,
    build_shell_command,
    ensure_remote_parent,
    list_files_from_find,
    list_remote_files,
    parse_devices,
    pull,
    push,
    remote_exists,
    remote_size,
    resolve_adb_path,
    run_shell,
)


def test_resolve_prefers_env(tmp_path):
    fake = tmp_path / "adb.exe"
    fake.write_text("")
    path = resolve_adb_path(env={"ADB_PATH": str(fake)}, exists=lambda p: p == str(fake), which=lambda _: None)
    assert path == str(fake)


def test_resolve_uses_default_when_present():
    path = resolve_adb_path(
        env={},
        exists=lambda p: p == DEFAULT_ADB_PATH,
        which=lambda _: None,
    )
    assert path == DEFAULT_ADB_PATH


def test_resolve_raises_when_missing():
    with pytest.raises(FileNotFoundError, match="ADB_PATH"):
        resolve_adb_path(env={}, exists=lambda _p: False, which=lambda _: None)


def test_parse_devices_extracts_serial_and_model():
    output = (
        "List of devices attached\n"
        "ABC123 device usb:1 product:foo model:Pixel_7 device:panther\n"
        "DEF456 unauthorized usb:2\n"
        "GHI789 device product:bar\n"
    )
    devices = parse_devices(output)
    assert devices[0] == ("ABC123", "Pixel_7")
    assert devices[1] == ("GHI789", None)


def test_list_files_from_find_strips_root_and_cr():
    output = "/sdcard/DCIM/Camera/a.jpg\r\n/sdcard/DCIM/b.jpg\n"
    files = list_files_from_find(output, root="/sdcard/DCIM")
    assert files == ["Camera/a.jpg", "b.jpg"]


def test_build_shell_command_quotes_parts_with_spaces():
    command = build_shell_command("stat", "-c", "%s", "--", "/sdcard/My File.jpg")
    assert command[0] == "sh"
    assert command[1] == "-c"
    assert shlex.quote("/sdcard/My File.jpg") in command[2]
    # round-trips back to the original tokens when a shell parses it
    assert shlex.split(command[2]) == ["stat", "-c", "%s", "--", "/sdcard/My File.jpg"]


def test_build_shell_command_leaves_safe_tokens_unquoted():
    command = build_shell_command("touch", "-m", "-d", "@1700000123", "/sdcard/photo.jpg")
    assert command == ["sh", "-c", "touch -m -d @1700000123 /sdcard/photo.jpg"]


@patch("filesync.adb.subprocess.run")
def test_remote_exists_quotes_spaced_path(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    remote_exists("adb", "serial", "/sdcard/DCIM/My Photo.jpg")

    argv = mock_run.call_args[0][0]
    assert argv[:4] == ["adb", "-s", "serial", "shell"]
    assert len(argv) == 5
    command = argv[4]
    assert shlex.quote("/sdcard/DCIM/My Photo.jpg") in command
    assert shlex.split(command) == ["ls", "/sdcard/DCIM/My Photo.jpg"]


@patch("filesync.adb.subprocess.run")
def test_remote_size_quotes_spaced_path(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="123\n", stderr="")
    remote_size("adb", "serial", "/sdcard/DCIM/My Photo.jpg")

    argv = mock_run.call_args[0][0]
    assert len(argv) == 5
    command = argv[4]
    assert shlex.quote("/sdcard/DCIM/My Photo.jpg") in command
    assert shlex.split(command) == ["stat", "-c", "%s", "/sdcard/DCIM/My Photo.jpg"]


@patch("filesync.adb.subprocess.run")
def test_list_remote_files_quotes_root_with_spaces(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    list_remote_files("adb", "serial", "/sdcard/My Folder")

    argv = mock_run.call_args[0][0]
    assert argv[:4] == ["adb", "-s", "serial", "shell"]
    assert len(argv) == 5
    command = argv[4]
    assert shlex.quote("/sdcard/My Folder") in command
    assert command.startswith("find ")


@patch("filesync.adb.run_shell")
def test_list_remote_files_keeps_stdout_on_nonzero_returncode(mock_run_shell):
    mock_run_shell.return_value = MagicMock(
        returncode=1,
        stdout="/sdcard/DCIM/a.jpg\n",
        stderr="find: /sdcard/DCIM/locked: Permission denied\n",
    )
    files = list_remote_files("adb", "serial", "/sdcard/DCIM")
    assert files == ["a.jpg"]


@patch("filesync.adb.subprocess.run")
def test_run_shell_passes_one_string_so_adb_does_not_split_sh_c(mock_run):
    """Regression: adb shell joins argv with spaces, turning
    ``sh -c ls '/sdcard/'`` into ``ls`` of Android root."""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    run_shell("adb", "serial", build_shell_command("ls", "-1p", "/sdcard/"))
    argv = mock_run.call_args[0][0]
    assert argv[:4] == ["adb", "-s", "serial", "shell"]
    assert len(argv) == 5
    assert argv[4:6] != ["sh", "-c"]
    assert shlex.split(argv[4]) == ["ls", "-1p", "/sdcard/"]
    kwargs = mock_run.call_args.kwargs
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"


@patch("filesync.adb.run_shell")
def test_ensure_remote_parent_mkdir_p(mock_run_shell):
    mock_run_shell.return_value = MagicMock(returncode=0, stdout="", stderr="")
    ensure_remote_parent("adb", "serial", "/sdcard/DCIM/Camera/pic.jpg")
    args = mock_run_shell.call_args[0]
    assert args[0] == "adb"
    assert args[2][:2] == ["sh", "-c"]
    assert shlex.split(args[2][2]) == ["mkdir", "-p", "/sdcard/DCIM/Camera"]


@patch("filesync.adb.subprocess.run")
def test_pull_and_push_hide_adb_byte_output(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    pull("adb", "serial", "/sdcard/a.jpg", r"D:\a.jpg")
    push("adb", "serial", r"D:\a.jpg", "/sdcard/a.jpg")
    assert mock_run.call_count == 2
    for call in mock_run.call_args_list:
        assert call.kwargs["capture_output"] is True
        assert call.kwargs["check"] is True


@patch("filesync.adb.run_shell")
def test_remote_tree_bytes_parses_du_sk(mock_run_shell):
    mock_run_shell.return_value = MagicMock(returncode=0, stdout="4096\t/sdcard/DCIM\n", stderr="")
    from filesync.adb import remote_tree_bytes

    assert remote_tree_bytes("adb", "serial", "/sdcard/DCIM") == 4096 * 1024
