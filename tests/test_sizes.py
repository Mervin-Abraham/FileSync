from pathlib import Path

from filesync.sizes import format_size, local_tree_size, parse_du_sk


def test_format_size_human_readable():
    assert format_size(0) == "0 B"
    assert format_size(500) == "500 B"
    assert format_size(1023) == "1023 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(2487219) == "2.4 MB"
    assert format_size(10 * 1024 * 1024) == "10 MB"
    assert format_size(3 * 1024 * 1024 * 1024) == "3.0 GB"
    assert format_size(None) == "?"


def test_parse_du_sk_tab_and_spaces():
    output = "12\t/sdcard/DCIM\n34 /sdcard/DCIM/Camera\n"
    sizes = parse_du_sk(output)
    assert sizes["/sdcard/DCIM"] == 12 * 1024
    assert sizes["/sdcard/DCIM/Camera"] == 34 * 1024


def test_child_folder_sizes_local(tmp_path: Path):
    from FileSync import Endpoint, child_folder_sizes

    src = tmp_path / "src"
    (src / "Android").mkdir(parents=True)
    (src / "DCIM").mkdir()
    (src / "DCIM" / "a.jpg").write_bytes(b"hello")
    sizes = child_folder_sizes(Endpoint("local", str(src)), "", ["Android", "DCIM"], None)
    assert sizes["Android"] == 0
    assert sizes["DCIM"] == 5


def test_local_tree_size(tmp_path: Path):
    folder = tmp_path / "pics"
    (folder / "a").mkdir(parents=True)
    (folder / "a" / "one.bin").write_bytes(b"abcd")
    (folder / "two.bin").write_bytes(b"xyz")
    assert local_tree_size(str(folder)) == 7


def test_format_duration_and_eta():
    from filesync.sizes import format_duration, format_eta, format_speed, eta_seconds

    assert format_duration(0.072) == "0.07s"
    assert format_duration(12.3) == "12.3s"
    assert format_duration(65) == "1:05"
    assert format_eta(None) == "--"
    assert format_eta(0) == "0:00"
    assert format_eta(252) == "4:12"
    assert format_speed(0) == "—"
    assert format_speed(33 * 1024 * 1024).endswith("/s")
    assert eta_seconds(0, 100) == 0.0
    assert eta_seconds(1000, 0) is None
    assert eta_seconds(1000, 100) == 10.0


def test_throughput_window_uses_last_five_copies():
    from filesync.sizes import ThroughputWindow

    window = ThroughputWindow(5)
    assert window.bytes_per_second() == 0.0
    window.add(1000, 1.0)
    window.add(3000, 1.0)
    assert window.bytes_per_second() == 2000.0
    for _ in range(5):
        window.add(5000, 1.0)
    assert window.bytes_per_second() == 5000.0
    assert window.overall_bytes_per_second() == (1000 + 3000 + 5 * 5000) / 7


def test_display_path_keeps_folder_and_shortens_filename():
    from filesync.sizes import display_path

    full = "Picsart/Picsart_22-04-19_14-06-49-459.png"
    assert display_path(full, max_len=80) == full
    short = display_path("Picsart/Picsart_22-04-19_14-06-49-459.png", max_len=28)
    assert short.startswith("Picsart/")
    assert short.endswith(".png")
    assert "…" in short
    assert not short.startswith("…")
