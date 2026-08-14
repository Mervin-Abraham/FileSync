"""Terminal UI helpers. Uses Rich when installed, plain print otherwise."""

from __future__ import annotations

from collections import deque

from filesync.sizes import (
    ThroughputWindow,
    display_path,
    eta_seconds,
    format_duration,
    format_eta,
    format_size,
    format_speed,
)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    _CONSOLE = Console()
    _RICH = True
except ImportError:
    _CONSOLE = None
    _RICH = False


def ask(prompt: str) -> str:
    if _RICH:
        return _CONSOLE.input(f"[cyan]{prompt}[/]")
    return input(prompt)


def header(title: str, subtitle: str = "") -> None:
    if _RICH:
        _CONSOLE.print()
        _CONSOLE.print(Rule(f"[bold cyan]{title}[/]", style="cyan"))
        if subtitle:
            _CONSOLE.print(f"  [dim]{subtitle}[/]")
        return
    print(f"\n{title}" + (f" — {subtitle}" if subtitle else ""))


def menu(title: str, options: list[tuple[str, str]]) -> None:
    """Print a numbered (or keyed) menu. options are (key, label)."""
    if _RICH:
        table = Table(show_header=False, box=None, padding=(0, 1), title=title, title_style="bold")
        table.add_column("key", style="cyan", justify="right", no_wrap=True)
        table.add_column("label")
        for key, label in options:
            table.add_row(f"{key})", label)
        _CONSOLE.print()
        _CONSOLE.print(table)
        return
    print(f"\n{title}")
    for key, label in options:
        print(f"  {key}) {label}")


def hint(message: str) -> None:
    if _RICH:
        _CONSOLE.print(f"  [dim]{message}[/]")
        return
    print(f"  {message}")


def info(message: str) -> None:
    if _RICH:
        _CONSOLE.print(message)
        return
    print(message)


def success(message: str) -> None:
    if _RICH:
        _CONSOLE.print(f"[green]{message}[/]")
        return
    print(message)


def warn(message: str) -> None:
    if _RICH:
        _CONSOLE.print(f"[yellow]{message}[/]")
        return
    print(message)


def error(message: str) -> None:
    if _RICH:
        _CONSOLE.print(f"[red]{message}[/]")
        return
    print(message)


def format_endpoint(endpoint) -> str:
    if endpoint.kind == "mtp":
        device = endpoint.device or "?"
        return f"Phone {device}  {endpoint.path}"
    return f"This PC  {endpoint.path}"


def recap(
    source,
    dest,
    ignored: list[str] | None = None,
    stats: dict | None = None,
) -> None:
    src = format_endpoint(source)
    dst = format_endpoint(dest)
    ignored = ignored or []
    stats = stats or {}
    files = stats.get("files")
    nbytes = stats.get("bytes")
    ignored_files = stats.get("ignored") or 0
    copy_files = stats.get("copy_files")
    copy_bytes = stats.get("copy_bytes")
    already_files = stats.get("already_files") or 0
    already_bytes = stats.get("already_bytes") or 0

    def _job_line(count, size) -> str:
        parts = []
        if count is not None:
            parts.append(f"{count:,} files")
        if size:
            parts.append(format_size(size))
        return " · ".join(parts)

    job = _job_line(files, nbytes)
    to_copy = _job_line(copy_files, copy_bytes) if already_files or already_bytes else ""
    already = _job_line(already_files, already_bytes)
    if _RICH:
        body = Text()
        body.append("Source  ", style="dim")
        body.append(src + "\n", style="bold")
        body.append("Dest    ", style="dim")
        body.append(dst, style="bold")
        if job:
            body.append("\nFiles   ", style="dim")
            body.append(job, style="bold")
        if to_copy:
            body.append("\nTo copy ", style="dim")
            body.append(to_copy, style="bold cyan")
        if already:
            body.append("\nAlready ", style="dim")
            body.append(already, style="green")
        if ignored:
            body.append("\nSkip    ", style="dim")
            skip = ", ".join(f"{item}/" for item in ignored)
            if ignored_files:
                skip += f"  ({ignored_files:,} files)"
            body.append(skip, style="yellow")
        _CONSOLE.print()
        _CONSOLE.print(Panel(body, title="Ready to copy", border_style="cyan", padding=(1, 2)))
        return
    print("\nReady to copy")
    print(f"  Source: {src}")
    print(f"  Dest:   {dst}")
    if job:
        print(f"  Files:   {job}")
    if to_copy:
        print(f"  To copy: {to_copy}")
    if already:
        print(f"  Already: {already}")
    if ignored:
        extra = f"  ({ignored_files:,} files)" if ignored_files else ""
        print("  Skip:   " + ", ".join(f"{item}/" for item in ignored) + extra)


def summary(counts: dict) -> None:
    copied = counts.get("copied", 0)
    skipped = counts.get("skipped", 0)
    failed = counts.get("failed", 0)
    ignored = counts.get("ignored", 0)
    copied_bytes = counts.get("copied_bytes", 0)
    skipped_bytes = counts.get("skipped_bytes", 0)
    failed_bytes = counts.get("failed_bytes", 0)
    if counts.get("stopped"):
        title = "Stopped"
    elif counts.get("error") or failed:
        title = "Stopped — partial copy"
    else:
        title = "Done"

    def _cell(n: int, nbytes: int = 0) -> str:
        if nbytes:
            return f"{n:,}   {format_size(nbytes)}"
        return f"{n:,}"

    if _RICH:
        table = Table(show_header=False, box=None, padding=(0, 2), title=title, title_style="bold")
        table.add_column("label")
        table.add_column("count", justify="right")
        table.add_row("[green]Copied[/]", f"[green]{_cell(copied, copied_bytes)}[/]")
        table.add_row("[dim]Skipped[/]", f"[dim]{_cell(skipped, skipped_bytes)}[/]")
        if ignored:
            table.add_row("[yellow]Ignored[/]", f"[yellow]{ignored:,}[/]")
        fail_style = "red" if failed else "dim"
        table.add_row(f"[{fail_style}]Failed[/]", f"[{fail_style}]{_cell(failed, failed_bytes)}[/]")
        elapsed = counts.get("elapsed_seconds")
        if elapsed:
            table.add_row("[dim]Elapsed[/]", f"[dim]{format_duration(elapsed)}[/]")
        _CONSOLE.print()
        _CONSOLE.print(table)
        return
    extra = f", Ignored: {ignored:,}" if ignored else ""
    print(
        f"{title}. Copied: {_cell(copied, copied_bytes)}, "
        f"Skipped: {_cell(skipped, skipped_bytes)}, Failed: {_cell(failed, failed_bytes)}{extra}"
    )


def _folder_label(name: str, nbytes: int | None = None, tag: str = "") -> str:
    parts = [f"{name}/"]
    if nbytes:
        parts.append(format_size(nbytes))
    if tag:
        parts.append(tag)
    return "  ".join(parts)


def folder_listing(
    path: str,
    dirs: list[str],
    file_count: int,
    at_root: bool = False,
    folder_bytes: int | None = None,
    dir_sizes: dict[str, int] | None = None,
) -> None:
    back_label = "Back" if at_root else "Up one level"
    options = [("0", "Use this folder"), ("b", back_label)]
    dir_sizes = dir_sizes or {}
    options.extend(
        (str(index), _folder_label(name, dir_sizes.get(name)))
        for index, name in enumerate(dirs, 1)
    )
    menu(f"Folder  {path}", options)
    bits = []
    if file_count:
        bits.append(f"{file_count:,} files here")
    if folder_bytes:
        bits.append(format_size(folder_bytes))
    if bits:
        hint(" · ".join(bits))


def ignore_listing(
    path: str,
    dirs: list[str],
    ignored_labels: set[str],
    at_root: bool,
    dir_sizes: dict[str, int] | None = None,
) -> None:
    back_label = "Back" if at_root else "Up one level"
    options = [("0", "Done — start copying"), ("b", back_label)]
    if not at_root:
        options.append(("s", "Skip this whole folder and go up"))
    dir_sizes = dir_sizes or {}
    for index, name in enumerate(dirs, 1):
        skipped = name in ignored_labels
        tag = "[won't copy]" if skipped else ""
        options.append((str(index), _folder_label(name, dir_sizes.get(name), tag)))
    menu(f"Skip folders  {path}", options)


def skip_folder_action(name: str, skipped: bool) -> None:
    title = f"{name}/  [won't copy]" if skipped else f"{name}/"
    skip_label = (
        "Copy this folder after all"
        if skipped
        else "Skip this folder and everything in it"
    )
    menu(title, [("1", "Look inside"), ("2", skip_label), ("b", "Back")])


def iter_files(relpaths: list[str]):
    """Yield relative paths with a Rich progress bar when available."""
    with sync_progress(relpaths) as progress:
        yield from progress


def sync_progress(relpaths: list[str], total_bytes: int = 0, copy_bytes: int = 0) -> "TransferDashboard":
    return TransferDashboard(relpaths, total_bytes=total_bytes, copy_bytes=copy_bytes)


class TransferDashboard:
    """Live last-5 transfer log plus byte-based speed, remaining, and ETA."""

    def __init__(self, relpaths: list[str], total_bytes: int = 0, copy_bytes: int = 0):
        self._relpaths = relpaths
        self.total_files = len(relpaths)
        self.done_files = 0
        self.total_bytes = max(0, int(total_bytes or 0))
        self.copy_bytes = max(0, int(copy_bytes or 0))
        if not self.copy_bytes:
            self.copy_bytes = self.total_bytes
        self.remaining_bytes = self.copy_bytes
        self.copied_bytes = 0
        self._log: deque[tuple[str, int, float, float]] = deque(maxlen=5)
        self._window = ThroughputWindow(5)
        self._current = "Starting…"
        self._current_size = 0
        self._live = None

    def __enter__(self):
        if _RICH and _CONSOLE is not None and getattr(_CONSOLE, "is_terminal", False):
            from rich.live import Live

            self._live = Live(self._render(), console=_CONSOLE, refresh_per_second=8, transient=False)
            self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._live is not None:
            return self._live.__exit__(exc_type, exc, tb)
        return False

    def __iter__(self):
        return iter(self._relpaths)

    def update_file(self, relpath: str, size: int) -> None:
        self._current = relpath
        self._current_size = max(0, int(size or 0))
        self._refresh()

    def record_copy(self, relpath: str, size: int, seconds: float) -> None:
        size = max(0, int(size or 0))
        seconds = max(0.0, float(seconds or 0))
        speed = size / seconds if seconds > 0 else 0.0
        self._log.append((relpath, size, seconds, speed))
        self._window.add(size, seconds)
        self.copied_bytes += size
        self.remaining_bytes = max(0, self.remaining_bytes - size)
        self.done_files += 1
        self._current = relpath
        self._current_size = size
        self._refresh()
        if self._live is None:
            print(
                f"  {relpath}  {format_size(size)}  {format_duration(seconds)}  {format_speed(speed)}"
            )

    def record_skip(self, size: int) -> None:
        self.done_files += 1
        self._refresh()

    def record_fail(self, size: int = 0) -> None:
        self.done_files += 1
        self._refresh()

    def advance(self, nbytes: int = 0) -> None:
        """Compatibility for older callers: count a finished file."""
        self.record_skip(nbytes)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def _path_width(self) -> int:
        if _CONSOLE is not None:
            return max(48, int(_CONSOLE.width) - 28)
        return 72

    def _show_path(self, relpath: str) -> str:
        return display_path(relpath, self._path_width())

    def _render(self):
        from rich.console import Group
        from rich.progress_bar import ProgressBar
        from rich.table import Table
        from rich.text import Text

        table = Table(
            show_header=True,
            box=None,
            padding=(0, 1),
            expand=True,
            title="Last 5 transfers",
            title_style="bold",
        )
        table.add_column("File", overflow="ellipsis", no_wrap=True, min_width=40, ratio=1)
        table.add_column("Size", justify="right", no_wrap=True)
        table.add_column("Time", justify="right", no_wrap=True)
        table.add_column("Speed", justify="right", no_wrap=True)
        rows = list(self._log)
        if not rows:
            table.add_row("—", "", "", "")
        else:
            for relpath, size, seconds, speed in rows:
                table.add_row(
                    self._show_path(relpath),
                    format_size(size),
                    format_duration(seconds),
                    format_speed(speed),
                )

        live_speed = self._window.bytes_per_second()
        eta_speed = self._window.overall_bytes_per_second() or live_speed
        remaining = self.remaining_bytes if self.copy_bytes else None
        eta = format_eta(eta_seconds(remaining or 0, eta_speed) if remaining is not None else None)
        frac = (self.done_files / self.total_files) if self.total_files else 0.0
        if self.copy_bytes:
            totals = f"{format_size(self.copied_bytes)} / {format_size(self.copy_bytes)} to copy"
            left = f"{format_size(self.remaining_bytes)} left"
        else:
            totals = format_size(self.copied_bytes)
            left = "left ?"

        current = self._show_path(self._current)
        if self._current_size:
            current = f"{current}  {format_size(self._current_size)}"

        status = Text()
        status.append(current + "\n")
        bar = ProgressBar(total=1.0, completed=frac, width=28)
        meta = Text.assemble(
            ("  ", ""),
            (totals, "bold"),
            (f"  {format_speed(live_speed)}", "cyan"),
            (f"  ETA {eta}", "cyan"),
            (f"  {left}", "dim"),
            (f"  {self.done_files:,}/{self.total_files:,}", "dim"),
        )
        return Group(table, Text(""), status, bar, meta)
