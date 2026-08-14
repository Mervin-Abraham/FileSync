import posixpath


def normalize_relpath(path: str, root: str | None = None) -> str:
    text = (path or "").replace("\\", "/").strip()
    root_text = (root or "").replace("\\", "/").rstrip("/")
    if root_text:
        if text == root_text:
            return ""
        prefix = root_text + "/"
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.lstrip("/")


def join_mtp_path(current: str, child: str) -> str:
    """Join an Android folder path. Never use Windows os.path for this."""
    child = (child or "").replace("\\", "/").strip()
    if child.startswith("/"):
        return child if child.endswith("/") else child + "/"
    base = (current or "/").replace("\\", "/").rstrip("/") or "/"
    return posixpath.join(base, child) + "/"


def folder_basename(path: str) -> str:
    """Last component of a local or Android folder path."""
    text = (path or "").replace("\\", "/").rstrip("/")
    if not text or text == "/":
        return ""
    return posixpath.basename(text)


def join_relpath(prefix: str, relpath: str) -> str:
    """Join dest-relative pieces with `/`. Empty prefix leaves relpath unchanged."""
    head = normalize_relpath(prefix)
    tail = normalize_relpath(relpath)
    if not head:
        return tail
    if not tail:
        return head
    return head + "/" + tail


def is_ignored(relpath: str, prefixes: list[str] | tuple[str, ...]) -> bool:
    """True if relpath is the skipped folder, a file in it, or anything nested under it."""
    rel = normalize_relpath(relpath).rstrip("/")
    if not rel:
        return False
    for prefix in prefixes:
        head = normalize_relpath(prefix).rstrip("/")
        if not head:
            continue
        if rel == head or rel.startswith(head + "/"):
            return True
    return False


def prune_ignore_prefixes(prefixes: list[str]) -> list[str]:
    """Drop child prefixes when a parent is already ignored."""
    unique = sorted({normalize_relpath(item) for item in prefixes if normalize_relpath(item)})
    unique.sort(key=lambda item: (item.count("/"), item))
    kept: list[str] = []
    for item in unique:
        if any(item == parent or item.startswith(parent + "/") for parent in kept):
            continue
        kept.append(item)
    return kept


def parent_mtp_path(current: str, root: str = "/sdcard/") -> str:
    """Parent of an Android folder, stopping at root."""
    root_norm = (root or "/").replace("\\", "/").rstrip("/") or "/"
    cur = (current or root).replace("\\", "/").rstrip("/") or "/"
    if cur == root_norm or cur == "/":
        return root_norm + "/"
    parent = posixpath.dirname(cur) or "/"
    if parent == "/":
        return "/"
    return parent + "/"
