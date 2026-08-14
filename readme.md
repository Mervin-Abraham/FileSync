# FileSync

FileSync is a Windows command-line tool for **one-way folder backup** between an Android phone and this PC. It copies photos, videos, documents, and other files you can see under `/sdcard/`, and it **keeps the original dates** on those files.

The usual job is a two-step phone move:

1. Old phone → folder on this PC  
2. That PC folder → new phone  

You run the same program both times. It is not a full phone clone.

---

## What it copies (and what it does not)

**Copies**

- Pictures, Camera, Download, Documents, and similar folders on Android shared storage (`/sdcard/…`)
- The same kinds of files from a folder on this PC back to a phone

**Does not copy**

- Apps, SMS, contacts, WhatsApp chats as an app backup, Google accounts, or anything that is not a normal file

---

## What you need (once)

Do this on the **Windows PC** you will use as the backup machine.

| Item | Notes |
|------|--------|
| Windows 10 or 11 | Run FileSync from **PowerShell**, not WSL |
| Python 3.10+ | In a terminal: `py -3 --version` |
| USB cable | Data cable, not charge-only |
| Android phone | **Developer options** → **USB debugging** on |

### 1. Python packages

In PowerShell:

```powershell
cd C:\Users\alex\Documents\Projects\FileSync
py -3 -m pip install -r requirements.txt
```

Use your real project path instead of `C:\Users\alex\Documents\Projects\FileSync`.

### 2. ADB (talks to the phone)

Install [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) or Android Studio so you have `adb.exe`.

FileSync looks for ADB in this order:

1. Environment variable `ADB_PATH` (full path to `adb.exe`)
2. `C:\Users\<you>\AppData\Local\Android\Sdk\platform-tools\adb.exe`
3. `adb` on your PATH

If ADB is somewhere else:

```powershell
$env:ADB_PATH = "C:\platform-tools\adb.exe"
```

### 3. Phone, first plug-in

1. Unlock the phone  
2. Plug it in  
3. Choose **File transfer / MTP** if Android asks  
4. Accept **Allow USB debugging** (tick “Always allow” if you trust this PC)

Check the PC can see the phone:

```powershell
adb devices
```

You want a line like `ABC123XYZ    device`. If it says `unauthorized`, unlock the phone and tap Allow.

---

## Start FileSync

Always from PowerShell, in the project folder:

```powershell
cd C:\Users\alex\Documents\Projects\FileSync
py -3 FileSync.py
```

Menus are numbered. You only type a number (or `b`) and Enter.

| Key | Meaning |
|-----|--------|
| `1`, `2`, `3`… | Pick that line |
| `0` | Use **this** phone folder / finish skipping |
| `b` | Back or up one folder |
| `Ctrl+C` | Stop a copy; you still get a summary of what finished |

---

## Example: Alex moves to a new phone

Made-up names so the steps are easy to copy. Swap in your folders and phones.

- Old phone: Pixel 6  
- New phone: Pixel 9  
- PC backup folder: `D:\Backups\Phone`

### Hop 1 — old phone → PC

1. Connect the **old** phone, then start FileSync.  
2. **Source:** `1) Phone`  
3. Walk to the folder you want, for example `/sdcard/DCIM/`:

```text
Folder  /sdcard/
  0)  Use this folder
  b)  Back
  1)  Android/
  2)  DCIM/
  3)  Download/
  4)  Pictures/
Choice: 2
```

```text
Folder  /sdcard/DCIM/
  0)  Use this folder
  b)  Up one level
  1)  Camera/
  2)  Screenshots/
Choice: 0
```

`0` means “backup **this** folder” (`DCIM`, including Camera and Screenshots).

4. **This source**

```text
  1)  Skip some folders
  2)  Copy everything
  b)  Back
```

- `2` — copy the whole folder (simplest).  
- `1` — then pick folders to skip (see [Skip folders](#skip-folders) below).

5. **Destination:** `2) This PC` → Browse… → `D:\Backups\Phone`

6. Read the recap, then `1) Start copy`:

```text
Ready to copy
  Source   Phone PIXEL6  /sdcard/DCIM/
  Dest     This PC  D:\Backups\Phone\DCIM
  Files    3,628 files · 8.2 GB
  To copy  3,628 files · 8.2 GB
```

FileSync puts the phone folder **under its own name** on the PC, so Camera and Picsart do not mix:

```text
D:\Backups\Phone\
  DCIM\
    Camera\
    Screenshots\
  Pictures\
    Picsart\
  .filesync-manifest.json    ← keep this file on the PC (see below)
```

If you choose `/sdcard/` itself as the source, there is no extra wrap folder.

7. After it finishes: `1) Copy another folder` (for Pictures, Download, …) or `2) Quit`.  
   The next run offers **Same as last** destination so you keep filling `D:\Backups\Phone`.

If you stop halfway, run the same copy again. Files already on the PC are skipped; only missing ones are pulled.

### Hop 2 — PC → new phone

1. Unplug the old phone. Plug in the **new** phone. USB debugging on, “Allow” tapped.  
2. `py -3 FileSync.py`  
3. **Source:** `2) This PC` → pick **`D:\Backups\Phone`** (the folder that contains `.filesync-manifest.json`, if you still have it)  
4. **This source:** `2) Copy everything` (or skip what you do not want on the new phone)  
5. **Destination:** `1) Phone` → walk to `/sdcard/` → `0) Use this folder`  
6. `1) Start copy`

Dates on the new phone match the old phone, not “today”. **`.filesync-manifest.json` is the source of truth.** If it is missing (or a file is not in it), FileSync uses the Windows file dates instead. After the files are on the new phone, those dates live **on the files**; the manifest is not required on the phone.

---

## Skip folders

After you pick a source, `1) Skip some folders` opens a list. Example:

```text
Skip folders  /sdcard/Pictures/
  0)  Done — start copying
  b)  Back
  1)  .thumbnails/
  2)  Picsart/
  3)  Instagram/
```

- Type `1` for `.thumbnails/`, then `2) Skip this folder and everything in it`  
- Type `2` for Picsart, then `1) Look inside` if you only want to skip a subfolder  
- `0` when the skip list looks right  

Skipped folders (and all files under them) are not copied. The recap shows them, for example:

```text
  Skip     .thumbnails/  (6,129 files)
  To copy  35 files · 14 MB
  Already  1,223 files · 7.5 GB
```

**Already** means those files are already on the destination (same path). They are not pulled again.

---

## While a copy runs

You will see the last few files, size, time, speed, how much is left, and an ETA:

```text
Last 5 transfers
  File                                      Size    Time     Speed
  Camera/IMG_20260301_142201.jpg            2.4 MB  0.08s    30 MB/s
  Camera/IMG_20260301_142205.jpg            1.8 MB  0.06s    31 MB/s

Camera/IMG_20260301_142210.jpg  2.2 MB
  1.2 GB / 3.1 GB to copy  31 MB/s  ETA 1:02  1.9 GB left  412/1,443
```

If something fails or you press Ctrl+C, FileSync still prints a **Copied / Skipped / Failed** summary.

---

## `.filesync-manifest.json` — keep this on the PC

**Source of truth for dates:** FileSync uses `.filesync-manifest.json` when it is there. If it is not available, it falls back to the Windows file dates.

The photos do **not** keep using this file after they have been copied. Original dates are also written **onto the files themselves**. The JSON is extra memory of those dates, so hop 2 does not have to trust Windows if something later changed “date modified”.

It lives in the **PC backup folder** (for example `D:\Backups\Phone\.filesync-manifest.json`). It is **not** copied onto the phone. Phone destinations may leave a copy under `logs\` on the PC, not under `/sdcard/`.

**Keep the PC copy** if you might still:

- Run hop 2 (PC → new phone), including a retry or a second phone  
- Copy more folders from the old phone into the same backup  
- Run the same copy again (resume / skip files already there)

Hop 2 should use this same PC folder as the source.

**If you already deleted it:** hop 2 still runs, using the Windows dates currently on the files. If hop 1 finished normally, those are still the original ones. If Explorer (or anything else) rewrote the dates, the new phone gets those newer dates instead. A folder that still looks like a phone backup (`DCIM`, `Pictures`, …) is treated as a backup root even without the JSON.

**You can ignore it** when you are done forever: old phone retired, new phone already has the files, you will not run FileSync on that backup again. Deleting it does **not** change dates already set on the phone.

Do **not** copy the backup with Explorer in the middle if you care about dates. Use FileSync for both hops.

---

## Menu cheat sheet

**Source / destination**

- `1` Phone (ADB)  
- `2` This PC (folder picker or typed path)  
- `b` Back  

**Phone folders**

- `0` Use this folder  
- `b` Up one level (at `/sdcard/` this leaves the picker)  
- Number: open that subfolder  

**After a copy**

- `1` Copy another folder  
- `2` Quit  

**Second copy onward**

- `1` Same destination as last time  
- `2` Choose a new destination  

---

## If something goes wrong

| Problem | What to try |
|---------|-------------|
| `ADB not found` | Install platform-tools; set `ADB_PATH` to `adb.exe` |
| `No devices found` | Cable, USB debugging, File transfer mode, unlock phone, `adb devices` |
| `unauthorized` | Unlock phone → Allow USB debugging |
| Copy is slow at `/sdcard/` listing | Normal: browsing is a simple folder list. The wait before **Ready to copy** is FileSync counting files |
| Run stopped at 2,000 / 3,000 files | Start the same source and dest again; already-copied files are skipped |
| New phone dates look like “today” | Keep `.filesync-manifest.json` — it is the source of truth. If it is gone, FileSync uses Windows file dates, so do not hop 2 from an Explorer copy that reset dates to today |
| Wondering if you can delete `.filesync-manifest.json` | Keep it until hop 2 is finished if you can. If it is already gone, hop 2 falls back to Windows file dates. Deleting it does not change dates already on the phone |

Logs (if you need them) are under `logs\` in the project folder.

---

## Tests (optional)

```powershell
py -3 -m pytest -q
```

---

## License and credits

Apache 2.0 — see `LICENSE`.

FileSync is developed by [Mervin Abraham](https://github.com/Mervin-Abraham).
