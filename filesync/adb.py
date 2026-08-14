from __future__ import annotations

import os
import posixpath
import shlex
import shutil
import subprocess

from filesync.paths import normalize_relpath
from filesync.sizes import parse_du_sk

DEFAULT_ADB_PATH = r"C:\Users\mervi\AppData\Local\Android\Sdk\platform-tools\adb.exe"


def resolve_adb_path(env=None, which=None, exists=None) -> str:
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    exists = os.path.exists if exists is None else exists
    tried = []
    env_path = env.get("ADB_PATH")
    if env_path:
        tried.append(env_path)
        if exists(env_path):
            return env_path
    tried.append(DEFAULT_ADB_PATH)
    if exists(DEFAULT_ADB_PATH):
        return DEFAULT_ADB_PATH
    on_path = which("adb")
    if on_path:
        tried.append(on_path)
        return on_path
    raise FileNotFoundError(
        "ADB not found. Tried: " + ", ".join(tried) + ". Set ADB_PATH or install platform-tools."
    )


def parse_devices(output: str) -> list[tuple[str, str | None]]:
    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        model = None
        for part in parts[2:]:
            if part.startswith("model:"):
                model = part.split(":", 1)[1]
        devices.append((serial, model))
    return devices


def list_files_from_find(output: str, root: str) -> list[str]:
    files = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        files.append(normalize_relpath(line, root=root))
    return [path for path in files if path]


def run_shell(adb: str, serial: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run a command on the device as a single `adb shell` string.

    `adb shell` concatenates extra argv with spaces and does not preserve
    argument boundaries. Passing ``sh -c SCRIPT`` as three argv entries
    becomes ``sh -c ls '/sdcard/'`` on the device, so ``-c`` only sees
    ``ls`` and lists ``/`` (Android root) instead of the intended folder.
    """
    if len(args) >= 3 and args[0] == "sh" and args[1] == "-c":
        remote = args[2]
    else:
        remote = " ".join(shlex.quote(part) for part in args)
    return subprocess.run(
        [adb, "-s", serial, "shell", remote],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def build_shell_command(*parts: str) -> list[str]:
    """Build a `run_shell` argv that quotes every part into a single `sh -c`
    string.

    `adb shell` joins the argv it is given with plain spaces before the
    remote shell sees it, so any part (typically a remote path) containing
    a space or shell metacharacter would otherwise be split into multiple
    arguments on the device. Quoting each part with `shlex.quote` and
    running it through one `sh -c` string keeps each part intact.
    """
    return ["sh", "-c", " ".join(shlex.quote(part) for part in parts)]


def list_remote_files(adb: str, serial: str, root: str) -> list[str]:
    command = f"find {shlex.quote(root)} -type f 2>/dev/null"
    result = run_shell(adb, serial, ["sh", "-c", command])
    return list_files_from_find(result.stdout or "", root)


def ensure_remote_parent(adb: str, serial: str, remote_file: str) -> None:
    """Create the parent directory of a remote file (`mkdir -p`)."""
    parent = posixpath.dirname((remote_file or "").rstrip("/"))
    if not parent or parent == "/":
        return
    run_shell(adb, serial, build_shell_command("mkdir", "-p", parent))


def _run_transfer(argv: list[str]) -> None:
    """Run adb push/pull without printing raw byte counts to the console."""
    subprocess.run(
        argv,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def push(adb: str, serial: str, local: str, remote: str) -> None:
    _run_transfer([adb, "-s", serial, "push", local, remote])


def pull(adb: str, serial: str, remote: str, local: str) -> None:
    _run_transfer([adb, "-s", serial, "pull", remote, local])


def remote_exists(adb: str, serial: str, remote: str) -> bool:
    result = run_shell(adb, serial, build_shell_command("ls", remote))
    text = (result.stderr or "") + (result.stdout or "")
    return "No such file or directory" not in text


def remote_size(adb: str, serial: str, remote: str) -> int | None:
    result = run_shell(adb, serial, build_shell_command("stat", "-c", "%s", remote))
    text = (result.stdout or "").strip()
    if text.isdigit():
        return int(text)
    return None


def remote_tree_bytes(adb: str, serial: str, remote: str) -> int | None:
    """Folder total from `du -sk`, or None if du fails."""
    result = run_shell(adb, serial, build_shell_command("du", "-sk", remote))
    if result.returncode != 0:
        return None
    sizes = parse_du_sk(result.stdout or "")
    key = (remote or "").rstrip("/")
    if key in sizes:
        return sizes[key]
    if sizes:
        return next(iter(sizes.values()))
    return None
