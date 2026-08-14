import os

import pytest

from FileSync import parse_kind, prompt_kind, select_device


def test_parse_kind():
    assert parse_kind("MTP") == "mtp"
    assert parse_kind(" local ") == "local"
    with pytest.raises(ValueError):
        parse_kind("usb")


def test_prompt_kind_retries_on_invalid_input_instead_of_crashing():
    answers = iter(["usb", "", " local "])
    result = prompt_kind("source", ask=lambda _prompt: next(answers))
    assert result == "local"


def test_prompt_kind_returns_immediately_on_first_valid_input():
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return "mtp"

    assert prompt_kind("destination", ask=ask) == "mtp"
    assert len(calls) == 1


def test_prompt_kind_accepts_numbered_choice():
    assert prompt_kind("source", ask=lambda _prompt: "1") == "mtp"
    assert prompt_kind("source", ask=lambda _prompt: "2") == "local"


def test_parse_ls_entries_splits_dirs_and_files():
    from FileSync import parse_ls_entries

    dirs, files = parse_ls_entries("DCIM/\nDownload/\nphoto.jpg\n")
    assert dirs == ["DCIM", "Download"]
    assert files == 1


def test_parse_ls_entries_includes_hidden_and_skips_dot_dot():
    from FileSync import parse_ls_entries

    dirs, files = parse_ls_entries("./\n../\n.thumbnails/\n.nomedia\nDCIM/\n")
    assert dirs == [".thumbnails", "DCIM"]
    assert files == 1


def test_mtp_listing_requests_hidden_names(monkeypatch):
    from FileSync import _mtp_listing

    calls = []

    def fake_run_shell(_adb, _serial, args):
        calls.append(args)
        return type("R", (), {"returncode": 0, "stdout": "./\n../\n.thumbnails/\nDCIM/\n", "stderr": ""})()

    monkeypatch.setattr("FileSync.run_shell", fake_run_shell)
    dirs, files = _mtp_listing("adb", "serial", "/sdcard/")
    assert calls[0][:2] == ["sh", "-c"]
    assert "-1ap" in calls[0][2]
    assert dirs == [".thumbnails", "DCIM"]
    assert files == 0


def test_traverse_mtp_uses_folder_numbers(monkeypatch):
    from FileSync import traverse_mtp_directories

    listings = {
        "/sdcard/": "DCIM/\nDownload/\n",
        "/sdcard/DCIM/": "Camera/\n",
    }

    def fake_run_shell(_adb, _serial, args):
        command = args[2] if args[:2] == ["sh", "-c"] else " ".join(args)
        path = command.split()[-1].strip("'")
        stdout = listings.get(path, "")
        return type("R", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    monkeypatch.setattr("FileSync.run_shell", fake_run_shell)
    answers = iter(["1", "0"])
    path = traverse_mtp_directories("adb", "serial", ask=lambda _p: next(answers))
    assert path == "/sdcard/DCIM/"


def test_traverse_mtp_b_goes_up_then_select(monkeypatch):
    from FileSync import traverse_mtp_directories

    listings = {
        "/sdcard/": "DCIM/\n",
        "/sdcard/DCIM/": "Camera/\n",
    }

    def fake_run_shell(_adb, _serial, args):
        command = args[2] if args[:2] == ["sh", "-c"] else " ".join(args)
        path = command.split()[-1].strip("'")
        stdout = listings.get(path, "")
        return type("R", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    monkeypatch.setattr("FileSync.run_shell", fake_run_shell)
    answers = iter(["1", "b", "0"])
    path = traverse_mtp_directories("adb", "serial", ask=lambda _p: next(answers))
    assert path == "/sdcard/"


def test_traverse_mtp_b_at_root_returns_none(monkeypatch):
    from FileSync import traverse_mtp_directories

    def fake_run_shell(_adb, _serial, args):
        return type("R", (), {"returncode": 0, "stdout": "DCIM/\n", "stderr": ""})()

    monkeypatch.setattr("FileSync.run_shell", fake_run_shell)
    path = traverse_mtp_directories("adb", "serial", ask=lambda _p: "b")
    assert path is None


def test_phone_folder_listing_does_not_run_du(monkeypatch):
    from FileSync import list_phone_directories

    commands = []

    def fake_run_shell(_adb, _serial, args):
        command = args[2] if args[:2] == ["sh", "-c"] else " ".join(args)
        commands.append(command)
        return type("R", (), {"returncode": 0, "stdout": "DCIM/\nDownload/\nphoto.jpg\n", "stderr": ""})()

    monkeypatch.setattr("FileSync.run_shell", fake_run_shell)
    dirs = list_phone_directories("adb", "serial", "/sdcard/")
    assert dirs == ["DCIM", "Download"]
    assert commands
    assert all("du " not in command and not command.startswith("du") for command in commands)


def test_prompt_kind_back_when_allowed():
    from FileSync import prompt_kind

    assert prompt_kind("destination", ask=lambda _p: "b", allow_back=True) is None


def test_prompt_local_directory_back():
    from FileSync import prompt_local_directory

    assert prompt_local_directory("source", ask=lambda _p: "b") is None


def test_select_device_back():
    from FileSync import select_device

    assert select_device([("AAA", None), ("BBB", None)], choose=lambda _p: "b") is None


def test_parse_ignore_choice():
    from FileSync import parse_ignore_choice

    assert parse_ignore_choice("0") == ("done", None)
    assert parse_ignore_choice("b") == ("back", None)
    assert parse_ignore_choice("i") == ("toggle_current", None)
    assert parse_ignore_choice("i2") == ("toggle", 2)
    assert parse_ignore_choice("s2") == ("toggle", 2)
    assert parse_ignore_choice("s 3") == ("toggle", 3)
    assert parse_ignore_choice("s") == ("toggle_current", None)
    assert parse_ignore_choice("1") == ("open", 1)


def test_prompt_ignore_mode():
    from FileSync import prompt_ignore_mode

    assert prompt_ignore_mode(ask=lambda _p: "1") == "ignore"
    assert prompt_ignore_mode(ask=lambda _p: "2") == "all"
    assert prompt_ignore_mode(ask=lambda _p: "b") == "back"


def test_prompt_ignore_folders_toggle_and_done(tmp_path):
    from FileSync import Endpoint, prompt_ignore_folders

    src = tmp_path / "src"
    (src / "Android").mkdir(parents=True)
    (src / "DCIM").mkdir()
    answers = iter(["1", "2", "0"])
    result = prompt_ignore_folders(Endpoint("local", str(src)), None, ask=lambda _p: next(answers))
    assert result == ["Android"]


def test_prompt_ignore_folders_shortcut_s1(tmp_path):
    from FileSync import Endpoint, prompt_ignore_folders

    src = tmp_path / "src"
    (src / "Android").mkdir(parents=True)
    (src / "DCIM").mkdir()
    answers = iter(["s1", "0"])
    result = prompt_ignore_folders(Endpoint("local", str(src)), None, ask=lambda _p: next(answers))
    assert result == ["Android"]


def test_prompt_ignore_folders_look_inside_then_skip(tmp_path):
    from FileSync import Endpoint, prompt_ignore_folders

    src = tmp_path / "src"
    (src / "Android" / "data").mkdir(parents=True)
    (src / "DCIM").mkdir()
    answers = iter(["1", "1", "s", "0"])
    result = prompt_ignore_folders(Endpoint("local", str(src)), None, ask=lambda _p: next(answers))
    assert result == ["Android"]


def test_prompt_skip_folder_action():
    from FileSync import prompt_skip_folder_action

    assert prompt_skip_folder_action("DCIM", False, ask=lambda _p: "1") == "open"
    assert prompt_skip_folder_action("DCIM", False, ask=lambda _p: "2") == "skip"
    assert prompt_skip_folder_action("DCIM", True, ask=lambda _p: "2") == "unskip"
    assert prompt_skip_folder_action("DCIM", False, ask=lambda _p: "b") == "back"



def test_prompt_next_choices():
    from FileSync import prompt_next

    assert prompt_next(ask=lambda _p: "1") == "again"
    assert prompt_next(ask=lambda _p: "2") == "quit"


def test_prompt_reuse_dest():
    from FileSync import Endpoint, prompt_reuse_dest

    dest = Endpoint("local", r"D:\backup")
    assert prompt_reuse_dest(dest, ask=lambda _p: "1") == "same"
    assert prompt_reuse_dest(dest, ask=lambda _p: "2") == "new"
    assert prompt_reuse_dest(dest, ask=lambda _p: "b") == "back"


def test_wrapped_dest_joins_prefix():
    from FileSync import Endpoint, wrapped_dest

    local = Endpoint("local", r"D:\backup")
    assert wrapped_dest(local, "DCIM").path == os.path.join(r"D:\backup", "DCIM")
    phone = Endpoint("mtp", "/sdcard/", device="X")
    assert wrapped_dest(phone, "DCIM").path == "/sdcard/DCIM/"
    assert wrapped_dest(local, "") is local


def test_confirm_copy_accepts_start_and_cancel():
    from FileSync import Endpoint, confirm_copy

    src = Endpoint("local", r"C:\src")
    dst = Endpoint("local", r"C:\dst")
    assert confirm_copy(src, dst, ask=lambda _p: "1") == "start"
    assert confirm_copy(src, dst, ask=lambda _p: "2") == "cancel"
    assert confirm_copy(src, dst, ask=lambda _p: "b") == "back"


def test_select_device_auto_when_one():
    assert select_device([("SERIAL1", "Pixel")], choose=lambda _: "99") == "SERIAL1"


def test_select_device_uses_number():
    answers = iter(["3", "2"])
    serial = select_device(
        [("AAA", None), ("BBB", "Pixel_7")],
        choose=lambda _prompt: next(answers),
    )
    assert serial == "BBB"
