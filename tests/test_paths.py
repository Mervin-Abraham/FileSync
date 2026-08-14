from filesync.paths import join_mtp_path, normalize_relpath, parent_mtp_path


def test_backslashes_become_slashes():
    assert normalize_relpath(r"Camera\IMG_001.jpg") == "Camera/IMG_001.jpg"


def test_strips_leading_slash():
    assert normalize_relpath("/sdcard/DCIM/Camera/a.jpg") == "sdcard/DCIM/Camera/a.jpg"


def test_relative_to_android_root():
    assert (
        normalize_relpath("/sdcard/DCIM/Camera/a.jpg", root="/sdcard/DCIM")
        == "Camera/a.jpg"
    )


def test_relative_to_root_with_trailing_slash():
    assert (
        normalize_relpath("/sdcard/DCIM/Camera/a.jpg", root="/sdcard/DCIM/")
        == "Camera/a.jpg"
    )


def test_already_relative_unchanged():
    assert normalize_relpath("Camera/a.jpg") == "Camera/a.jpg"


def test_join_mtp_path_does_not_use_windows_drive_rules():
    assert join_mtp_path("/sdcard/", "DCIM") == "/sdcard/DCIM/"
    assert join_mtp_path("/sdcard/DCIM/", "Camera") == "/sdcard/DCIM/Camera/"
    assert join_mtp_path("/sdcard/", "/storage/emulated/0") == "/storage/emulated/0/"


def test_folder_basename_local_and_mtp():
    from filesync.paths import folder_basename

    assert folder_basename(r"D:\Personal\Phone Backup\Picsart") == "Picsart"
    assert folder_basename("/sdcard/DCIM/") == "DCIM"
    assert folder_basename("/sdcard/") == "sdcard"
    assert folder_basename("/") == ""


def test_join_relpath_prefixes_when_present():
    from filesync.paths import join_relpath

    assert join_relpath("DCIM", "Camera/a.jpg") == "DCIM/Camera/a.jpg"
    assert join_relpath("", "Camera/a.jpg") == "Camera/a.jpg"
    assert join_relpath("Picsart", "") == "Picsart"


def test_parent_mtp_path_stops_at_sdcard():
    assert parent_mtp_path("/sdcard/DCIM/Camera/", "/sdcard/") == "/sdcard/DCIM/"
    assert parent_mtp_path("/sdcard/", "/sdcard/") == "/sdcard/"
    assert parent_mtp_path("/sdcard/sdcard/data/product/", "/sdcard/") == "/sdcard/sdcard/data/"


def test_is_ignored_matches_folder_and_children():
    from filesync.paths import is_ignored

    assert is_ignored("Android/data/x.bin", ["Android"]) is True
    assert is_ignored("Android/foo.txt", ["Android"]) is True
    assert is_ignored("Android", ["Android/"]) is True
    assert is_ignored("Android", ["Android"]) is True
    assert is_ignored("DCIM/a.jpg", ["Android"]) is False


def test_prune_ignore_prefixes_drops_children():
    from filesync.paths import prune_ignore_prefixes

    assert prune_ignore_prefixes(["Android", "Android/data", "DCIM"]) == ["Android", "DCIM"]

