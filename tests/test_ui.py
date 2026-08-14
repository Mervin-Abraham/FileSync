from filesync.copy import Endpoint
from filesync import ui


def test_format_endpoint_local():
    assert ui.format_endpoint(Endpoint("local", r"D:\backup")) == r"This PC  D:\backup"


def test_format_endpoint_phone():
    endpoint = Endpoint("mtp", "/sdcard/DCIM/", device="ABC123")
    assert ui.format_endpoint(endpoint) == "Phone ABC123  /sdcard/DCIM/"


def test_iter_files_yields_all_paths():
    paths = ["a.jpg", "b/c.png"]
    assert list(ui.iter_files(paths)) == paths


def test_summary_and_recap_do_not_crash():
    ui.header("FileSync", "test")
    ui.menu("Select source", [("1", "Phone (ADB)"), ("2", "This PC")])
    ui.recap(Endpoint("local", r"C:\src"), Endpoint("mtp", "/sdcard/", device="X"))
    ui.summary({"copied": 2, "skipped": 1, "failed": 0})
    ui.summary({"copied": 0, "skipped": 0, "failed": 3})
    ui.folder_listing("/sdcard/", ["DCIM", "Download"], 4)
    ui.ignore_listing("/sdcard/", ["DCIM", "Android"], {"Android"}, at_root=True)
    ui.folder_listing("/sdcard/DCIM/", ["Camera"], 12, folder_bytes=2487219, dir_sizes={"Camera": 2487219})
    ui.summary({"copied": 1, "skipped": 0, "failed": 0, "copied_bytes": 2487219, "skipped_bytes": 0})
    ui.skip_folder_action("DCIM", False)
    ui.skip_folder_action("Android", True)
    ui.summary({"copied": 1, "skipped": 0, "failed": 2, "error": "disk full", "stopped": False})
    ui.summary({"copied": 4, "skipped": 1, "failed": 0, "stopped": True, "copied_bytes": 100})
    ui.recap(Endpoint("local", r"C:\src"), Endpoint("local", r"D:\dst"), ignored=["Android"])
    ui.recap(
        Endpoint("local", r"C:\src"),
        Endpoint("local", r"D:\dst"),
        ignored=["Android"],
        stats={"files": 3628, "bytes": 2487219 * 100, "ignored": 12, "copy_files": 1443, "copy_bytes": 1000, "already_files": 2185, "already_bytes": 5000},
    )


def test_transfer_dashboard_remaining_and_last_five():
    paths = [f"f{i}.bin" for i in range(7)]
    dash = ui.TransferDashboard(paths, total_bytes=7000, copy_bytes=6000)
    with dash:
        dash.record_copy("f0.bin", 1000, 0.1)
        dash.record_skip(1000)
        for index in range(2, 7):
            dash.record_copy(f"f{index}.bin", 1000, 0.1)
    assert dash.remaining_bytes == 0
    assert dash.copied_bytes == 6000
    assert len(dash._log) == 5
    names = [row[0] for row in dash._log]
    assert names == ["f2.bin", "f3.bin", "f4.bin", "f5.bin", "f6.bin"]
    assert "f0.bin" not in names
    assert dash._window.bytes_per_second() > 0


def test_transfer_dashboard_skip_does_not_change_copy_remaining():
    dash = ui.TransferDashboard(["a.bin", "b.bin"], total_bytes=2000, copy_bytes=1000)
    with dash:
        dash.record_skip(1000)
        assert dash.remaining_bytes == 1000
        dash.record_copy("b.bin", 1000, 0.5)
        assert dash.remaining_bytes == 0
    assert dash._window.overall_bytes_per_second() == 2000.0
