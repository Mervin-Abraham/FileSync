from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from tkinter import Tk, filedialog

from filesync.adb import build_shell_command, parse_devices, resolve_adb_path, run_shell
from filesync.copy import Endpoint, dest_prefix_for, source_job_stats, sync_directories
from filesync.manifest import load_manifest
from filesync.paths import is_ignored, join_mtp_path, join_relpath, parent_mtp_path, prune_ignore_prefixes
from filesync.sizes import local_tree_size, parse_du_sk
from filesync import ui

LOG_DIR = "logs"
MTP_ROOT = "/sdcard/"


def parse_kind(text: str) -> str:
    """Parse a source/dest kind answer into 'mtp' or 'local'."""
    kind = text.strip().lower()
    if kind not in ("mtp", "local"):
        raise ValueError(f"Invalid kind: {text!r}. Expected 'mtp' or 'local'.")
    return kind


def select_device(devices: list[tuple[str, str | None]], choose) -> str | None:
    """Return a device serial, or None if the user goes back.

    Auto-selects when there is exactly one device.
    """
    if len(devices) == 1:
        serial, model = devices[0]
        label = f"{serial} - {model}" if model else serial
        ui.success(f"Using device: {label}")
        return serial

    options = [
        (str(index), f"{serial} - {model}" if model else serial)
        for index, (serial, model) in enumerate(devices, 1)
    ]
    options.append(("b", "Back"))
    ui.menu("Available devices", options)
    while True:
        answer = choose("Choice: ").strip()
        if answer.lower() == "b":
            return None
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(devices):
                return devices[index - 1][0]
        ui.warn("Enter a number from the list, or b to go back.")


def select_local_directory(title: str) -> str:
    root = Tk()
    root.withdraw()
    try:
        path = filedialog.askdirectory(title=title)
    finally:
        root.destroy()
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.abspath(path)


def prompt_local_directory(label: str, ask=ui.ask, browse=select_local_directory) -> str | None:
    while True:
        ui.menu(f"{label} folder", [("1", "Browse…"), ("2", "Type a path"), ("b", "Back")])
        choice = ask("Choice: ").strip()
        if choice.lower() == "b":
            return None
        if choice == "1":
            return browse(f"Select {label} directory")
        if choice == "2":
            typed = ask("Path: ").strip().strip('"')
            if os.path.isdir(typed):
                return os.path.abspath(typed)
            ui.warn("That path is not a folder.")
            continue
        ui.warn("Enter 1, 2, or b.")


def parse_ls_entries(output: str) -> tuple[list[str], int]:
    """Split `ls -1ap` output into directory names and a file count.

    Includes hidden names (`.thumbnails`, …). Skips `.` and `..`.
    """
    dirs: list[str] = []
    files = 0
    for line in output.splitlines():
        entry = line.strip()
        if not entry or entry in (".", "..", "./", "../"):
            continue
        if entry.endswith("/"):
            name = entry.rstrip("/")
            if name:
                dirs.append(name)
        else:
            files += 1
    return dirs, files


def _mtp_listing(adb: str, serial: str, current_path: str) -> tuple[list[str], int] | None:
    tries = (("-1ap",), ("-1a",), ("-1p",), ("-1",), ("-a",))
    result = None
    for flags in tries:
        result = run_shell(adb, serial, build_shell_command("ls", *flags, current_path))
        if result.returncode == 0:
            break
    if result is None or result.returncode != 0:
        ui.error(result.stderr.strip() if result and result.stderr else f"Failed to list {current_path}")
        return None
    stdout = result.stdout or ""
    raw_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    has_dir_marks = any(line.endswith("/") for line in raw_lines)
    dirs, files = parse_ls_entries(stdout)
    if raw_lines and not has_dir_marks:
        dirs = [
            line.rstrip("/")
            for line in raw_lines
            if line not in (".", "..", "./", "../")
        ]
        files = 0
    return dirs, files


_mtp_size_cache: dict[tuple[str, str], dict[str, int]] = {}


def _mtp_folder_sizes(adb: str, serial: str, folder: str) -> dict[str, int]:
    """One-level tree sizes from `du -d 1 -sk`. Cached so going back is cheap.

    Do not fall back to `du -sk` on the same folder: that walks the whole
    tree again for a single total, which is why `/sdcard/` felt frozen.
    """
    if not folder:
        return {}
    cache_key = (serial, folder.rstrip("/") or folder)
    cached = _mtp_size_cache.get(cache_key)
    if cached is not None:
        return cached
    result = run_shell(adb, serial, build_shell_command("du", "-d", "1", "-sk", folder))
    sizes = parse_du_sk(result.stdout or "") if result.returncode == 0 else {}
    _mtp_size_cache[cache_key] = sizes
    return sizes


def child_folder_sizes(source: Endpoint, rel: str, names: list[str], adb: str | None) -> dict[str, int]:
    if not names:
        return {}
    if source.kind == "local":
        base = os.path.join(source.path, *rel.split("/")) if rel else source.path
        return {name: local_tree_size(os.path.join(base, name)) for name in names}
    folder = join_mtp_path(source.path, rel) if rel else source.path
    if folder.rstrip("/") == "/sdcard":
        return {}
    raw = _mtp_folder_sizes(adb or "", source.device or "", folder)
    mapped: dict[str, int] = {}
    for name in names:
        key = join_mtp_path(folder, name).rstrip("/")
        if key in raw:
            mapped[name] = raw[key]
    return mapped


def list_phone_directories(adb: str, serial: str, current_path: str) -> list[str] | None:
    listing = _mtp_listing(adb, serial, current_path)
    if listing is None:
        return None
    dirs, files = listing
    at_root = current_path.rstrip("/") == MTP_ROOT.rstrip("/")
    ui.folder_listing(current_path, dirs, files, at_root=at_root)
    return dirs


def traverse_mtp_directories(
    adb: str,
    serial: str,
    current_path: str = MTP_ROOT,
    ask=ui.ask,
) -> str | None:
    """Walk phone folders. `b` goes up; at `/sdcard/` it returns None (back)."""
    if not current_path:
        current_path = MTP_ROOT
    while True:
        directories = list_phone_directories(adb, serial, current_path)
        if directories is None:
            if current_path.rstrip("/") != MTP_ROOT.rstrip("/"):
                current_path = MTP_ROOT
                continue
            return None

        choice = ask("Choice: ").strip()
        lowered = choice.lower()
        if lowered in ("0", "select"):
            return current_path
        if lowered in ("b", ".."):
            parent = parent_mtp_path(current_path, MTP_ROOT)
            if parent == current_path or current_path.rstrip("/") == MTP_ROOT.rstrip("/"):
                return None
            current_path = parent
            continue
        if choice.startswith("/"):
            current_path = join_mtp_path("/", choice.lstrip("/"))
            continue
        if choice.isdigit():
            index = int(choice)
            if 1 <= index <= len(directories):
                current_path = join_mtp_path(current_path, directories[index - 1])
                continue
        if choice in directories:
            current_path = join_mtp_path(current_path, choice)
            continue
        ui.warn("Enter 0 to use this folder, b to go back, or a folder number.")


def run_once(
    source: Endpoint,
    dest: Endpoint,
    adb: str | None,
    dest_prefix: str = "",
    ignore_prefixes: list[str] | tuple[str, ...] = (),
    planned: dict | None = None,
) -> dict:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("main")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(os.path.join(LOG_DIR, "main_logger.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    return sync_directories(
        source,
        dest,
        adb=adb,
        logger=logger,
        dest_prefix=dest_prefix,
        ignore_prefixes=ignore_prefixes,
        planned=planned,
    )


def _prompt_mtp_endpoint(start_path: str = MTP_ROOT) -> tuple[Endpoint | None, str | None]:
    """Resolve ADB, pick a device, walk folders. None endpoint means user went back."""
    try:
        adb = resolve_adb_path()
    except FileNotFoundError as exc:
        ui.error(str(exc))
        return Endpoint(kind="mtp", path=""), None

    try:
        output = subprocess.check_output([adb, "devices", "-l"], encoding="utf-8", errors="replace")
    except (subprocess.CalledProcessError, OSError) as exc:
        ui.error(f"Error listing devices: {exc}")
        return Endpoint(kind="mtp", path=""), adb

    devices = parse_devices(output)
    if not devices:
        ui.warn("No devices found. Please connect a device and try again.")
        return Endpoint(kind="mtp", path=""), adb

    serial = select_device(devices, choose=ui.ask)
    if serial is None:
        return None, adb
    path = traverse_mtp_directories(adb, serial, current_path=start_path or MTP_ROOT)
    if path is None:
        return None, adb
    return Endpoint(kind="mtp", path=path, device=serial), adb


def prompt_kind(label: str, ask=ui.ask, allow_back: bool = False) -> str | None:
    """Prompt for source/dest kind. Accepts 1/2 or mtp/local. None if back."""
    options = [("1", "Phone (ADB)"), ("2", "This PC")]
    if allow_back:
        options.append(("b", "Back"))
    while True:
        ui.menu(f"Select {label}", options)
        raw = ask("Choice: ")
        if allow_back and raw.strip().lower() == "b":
            return None
        try:
            if raw.strip() == "1":
                return "mtp"
            if raw.strip() == "2":
                return "local"
            return parse_kind(raw)
        except ValueError:
            ui.warn("Enter 1 or 2" + (", or b." if allow_back else "."))


def _prompt_endpoint(
    label: str,
    allow_back: bool = False,
    start_mtp: str = MTP_ROOT,
) -> tuple[Endpoint | None, str | None]:
    while True:
        kind = prompt_kind(label, allow_back=allow_back)
        if kind is None:
            return None, None
        if kind == "mtp":
            endpoint, adb = _prompt_mtp_endpoint(start_path=start_mtp)
            if endpoint is None:
                continue
            return endpoint, adb
        path = prompt_local_directory(label)
        if path is None:
            continue
        return Endpoint(kind="local", path=path), None


def list_child_directory_names(source: Endpoint, rel: str, adb: str | None) -> list[str] | None:
    if source.kind == "local":
        path = os.path.join(source.path, *rel.split("/")) if rel else source.path
        if not os.path.isdir(path):
            return None
        names = []
        for name in sorted(os.listdir(path), key=str.lower):
            if os.path.isdir(os.path.join(path, name)):
                names.append(name)
        return names
    folder = join_mtp_path(source.path, rel) if rel else source.path
    listing = _mtp_listing(adb, source.device, folder)
    if listing is None:
        return None
    return listing[0]


def parse_ignore_choice(text: str) -> tuple[str, int | None]:
    raw = text.strip().lower()
    if raw in ("0", "done"):
        return "done", None
    if raw in ("b", ".."):
        return "back", None
    if raw == "s":
        return "toggle_current", None
    if raw.isdigit():
        return "open", int(raw)
    return "unknown", None


def prompt_ignore_mode(ask=ui.ask) -> str:
    ui.menu(
        "This source",
        [("1", "Skip some folders"), ("2", "Copy everything"), ("b", "Back")],
    )
    while True:
        answer = ask("Choice: ").strip().lower()
        if answer in ("1", "i"):
            return "ignore"
        if answer in ("2", "all"):
            return "all"
        if answer == "b":
            return "back"
        ui.warn("Enter 1, 2, or b.")


def prompt_skip_folder_action(name: str, skipped: bool, ask=ui.ask) -> str:
    ui.skip_folder_action(name, skipped)
    while True:
        answer = ask("Choice: ").strip().lower()
        if answer in ("1", "open", "o"):
            return "open"
        if answer in ("2", "s", "skip", "unskip"):
            return "unskip" if skipped else "skip"
        if answer == "b":
            return "back"
        ui.warn("Enter 1, 2, or b.")


def _toggle_ignore(ignored: set[str], rel: str) -> set[str]:
    if rel in ignored:
        ignored.discard(rel)
    elif is_ignored(rel, list(ignored)):
        ui.warn("A parent folder is already skipped.")
    else:
        ignored.add(rel)
        ignored = set(prune_ignore_prefixes(list(ignored)))
    return ignored


def prompt_ignore_folders(source: Endpoint, adb: str | None, ask=ui.ask) -> list[str] | None:
    ignored: set[str] = set()
    current = ""
    while True:
        dirs = list_child_directory_names(source, current, adb)
        if dirs is None:
            ui.warn("Could not list folders.")
            if not current:
                return None
            current = join_relpath("", "/".join(current.split("/")[:-1])) if "/" in current else ""
            continue
        labels = {name for name in dirs if is_ignored(join_relpath(current, name), list(ignored))}
        display = source.path if not current else (
            os.path.join(source.path, *current.split("/")) if source.kind == "local"
            else join_mtp_path(source.path, current)
        )
        ui.ignore_listing(display, dirs, labels, at_root=not current, dir_sizes=child_folder_sizes(source, current, dirs, adb))
        action, number = parse_ignore_choice(ask("Choice: "))
        if action == "done":
            return prune_ignore_prefixes(list(ignored))
        if action == "back":
            if not current:
                return None
            current = "/".join(current.split("/")[:-1])
            continue
        if action == "toggle_current":
            if not current:
                ui.warn("Pick a numbered folder first, then choose Skip.")
                continue
            already = current in ignored
            ignored = _toggle_ignore(ignored, current)
            if not already and current in ignored:
                current = "/".join(current.split("/")[:-1])
            continue
        if action == "open" and number is not None:
            if not (1 <= number <= len(dirs)):
                ui.warn("Enter a folder number from the list.")
                continue
            name = dirs[number - 1]
            rel = join_relpath(current, name)
            skipped = is_ignored(rel, list(ignored))
            next_action = prompt_skip_folder_action(name, skipped, ask=ask)
            if next_action == "open":
                current = rel
            elif next_action in ("skip", "unskip"):
                ignored = _toggle_ignore(ignored, rel)
            continue
        ui.warn("Type a folder number, 0 when finished, or b to go back.")


def wrapped_dest(dest: Endpoint, prefix: str) -> Endpoint:
    """Dest path as shown in recap, including the wrap folder when used."""
    if not prefix:
        return dest
    if dest.kind == "local":
        return Endpoint("local", os.path.join(dest.path, prefix), dest.device)
    return Endpoint("mtp", join_mtp_path(dest.path, prefix), dest.device)


def prompt_reuse_dest(last_dest: Endpoint, ask=ui.ask) -> str:
    """Second+ attempt: keep the previous dest or pick a new one."""
    ui.menu(
        "Destination",
        [
            ("1", f"Same as last — {ui.format_endpoint(last_dest)}"),
            ("2", "Choose new…"),
            ("b", "Back"),
        ],
    )
    while True:
        answer = ask("Choice: ").strip().lower()
        if answer in ("1", "same", "y", "yes"):
            return "same"
        if answer in ("2", "new", "n", "no"):
            return "new"
        if answer == "b":
            return "back"
        ui.warn("Enter 1, 2, or b.")


def prompt_next(ask=ui.ask) -> str:
    """After a copy: another folder or quit."""
    ui.menu(
        "Next",
        [
            ("1", "Copy another folder"),
            ("2", "Quit"),
        ],
    )
    while True:
        answer = ask("Choice: ").strip().lower()
        if answer in ("1", "again", "y", "yes"):
            return "again"
        if answer in ("2", "3", "q", "quit"):
            return "quit"
        ui.warn("Enter 1 or 2.")


def confirm_copy(
    source: Endpoint,
    dest: Endpoint,
    ask=ui.ask,
    ignored: list[str] | None = None,
    stats: dict | None = None,
) -> str:
    ui.recap(source, dest, ignored=ignored, stats=stats)
    ui.menu("Then", [("1", "Start copy"), ("2", "Cancel"), ("b", "Back")])
    while True:
        answer = ask("Choice: ").strip().lower()
        if answer in ("1", "c", "confirm", "y", "yes"):
            return "start"
        if answer in ("2", "n", "no"):
            return "cancel"
        if answer == "b":
            return "back"
        ui.warn("Enter 1, 2, or b.")


def main() -> None:
    run_id = datetime.now().strftime("%d %B %Y - %H:%M:%S")
    ui.header("FileSync", run_id)
    ui.hint("Copy files phone ↔ PC and keep original dates.")

    last_dest: Endpoint | None = None
    last_dest_adb: str | None = None
    last_mtp_source = MTP_ROOT
    last_mtp_dest = MTP_ROOT

    while True:
        source, source_adb = _prompt_endpoint("source", start_mtp=last_mtp_source)
        if source is None or not source.path:
            ui.warn("Invalid directories selected, please try again.")
            continue
        ui.info(f"Source: {ui.format_endpoint(source)}")
        if source.kind == "mtp":
            last_mtp_source = source.path

        ignore_mode = prompt_ignore_mode()
        if ignore_mode == "back":
            continue
        ignore_prefixes: list[str] = []
        if ignore_mode == "ignore":
            chosen = prompt_ignore_folders(source, source_adb)
            if chosen is None:
                continue
            ignore_prefixes = chosen

        dest: Endpoint | None
        dest_adb: str | None
        if last_dest and last_dest.path:
            reuse = prompt_reuse_dest(last_dest)
            if reuse == "back":
                continue
            if reuse == "same":
                dest, dest_adb = last_dest, last_dest_adb
                ui.info(f"Dest:   {ui.format_endpoint(dest)}")
            else:
                dest, dest_adb = _prompt_endpoint(
                    "destination",
                    allow_back=True,
                    start_mtp=last_mtp_dest,
                )
                if dest is None:
                    continue
                ui.info(f"Dest:   {ui.format_endpoint(dest) if dest.path else '(none)'}")
        else:
            dest, dest_adb = _prompt_endpoint(
                "destination",
                allow_back=True,
                start_mtp=last_mtp_dest,
            )
            if dest is None:
                continue
            ui.info(f"Dest:   {ui.format_endpoint(dest) if dest.path else '(none)'}")

        if not dest or not dest.path:
            ui.warn("Invalid directories selected, please try again.")
            continue
        last_dest = dest
        last_dest_adb = dest_adb
        if dest.kind == "mtp":
            last_mtp_dest = dest.path

        prefix = dest_prefix_for(source)
        if source.kind == "local" and dest.kind == "mtp" and load_manifest(source.path) is None:
            ui.warn(
                "No .filesync-manifest.json in this PC folder. "
                "Using Windows file dates as fallback."
            )
        adb = dest_adb or source_adb
        if (source.kind == "mtp" or dest.kind == "mtp") and adb is None:
            try:
                adb = resolve_adb_path()
            except FileNotFoundError as exc:
                ui.error(str(exc))
                continue
        ui.hint("Counting files and size…")
        stats = source_job_stats(
            source, adb, ignore_prefixes, dest=dest, dest_prefix=prefix
        )
        decision = confirm_copy(
            source,
            wrapped_dest(dest, prefix),
            ignored=ignore_prefixes,
            stats=stats,
        )
        if decision == "back":
            continue
        if decision == "cancel":
            ui.warn("Cancelled.")
        else:
            try:
                counts = run_once(
                    source,
                    dest,
                    adb,
                    dest_prefix=prefix,
                    ignore_prefixes=ignore_prefixes,
                    planned=stats,
                )
                last_dest = dest
                last_dest_adb = dest_adb
            except Exception as exc:
                ui.error(f"Error during sync: {exc}")
                counts = {
                    "copied": 0,
                    "skipped": 0,
                    "failed": 0,
                    "ignored": 0,
                    "copied_bytes": 0,
                    "skipped_bytes": 0,
                    "failed_bytes": 0,
                    "stopped": False,
                    "error": str(exc),
                    "elapsed_seconds": 0.0,
                }
            ui.summary(counts)

        action = prompt_next()
        if action == "quit":
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        ui.warn("\nCancelled.")
