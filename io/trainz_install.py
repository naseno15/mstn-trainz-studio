"""Scan zip/CDP drops and stage them for TrainzUtil installCDP / installfrompath.

TrainzUtil talks to one asset database. Callers install one job at a time unless
the user raises the parallel cap. The Launcher must be running (Advanced debug
tools on) or database commands answer "Trainz is not running".
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import queue
import re
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .cdp import browse_cdp, format_bytes, load_cdp, open_cdp, read_file_bytes

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class InstallJob:
    id: str
    label: str
    kind: str  # cdp | zip-cdp | zip-folder | cdp-inner | zip-nested | info
    detail: str
    can_install: bool
    source: Path
    member: str = ""
    chain: tuple[str, ...] = ()
    asset_kuid: str = ""
    checked: bool = False

    def row(self) -> dict[str, object]:
        return {
            "jobId": self.id,
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
            "canInstall": self.can_install,
            "checked": self.checked and self.can_install,
            "openable": self.kind == "zip-nested",
        }


@dataclass
class SourceScan:
    path: Path
    kind: str
    jobs: list[InstallJob] = field(default_factory=list)


def launcher_blocked(text: str) -> bool:
    return "not running" in (text or "").lower()


def find_trainzutil(saved: str = "") -> Path | None:
    """Saved path, env, then TrainzUtil.exe under steamapps/common on each drive.

    ponytail: one directory listing per drive root plus a few known Steam tails.
    A library buried deeper than that needs Browse.
    """
    for cand in _explicit_trainzutil(saved):
        if cand.is_file():
            return cand
    for common in steam_common_dirs():
        hit = trainzutil_under_common(common)
        if hit is not None:
            return hit
    return None


def _explicit_trainzutil(saved: str) -> list[Path]:
    env_exe = os.environ.get("TRAINZUTIL", "")
    env_home = os.environ.get("TRAINZ_HOME") or os.environ.get("TRS22_HOME") or ""
    out: list[Path] = []
    if saved:
        out.append(Path(saved))
    if env_exe:
        out.append(Path(env_exe))
    if env_home:
        out.append(Path(env_home) / "TrainzUtil.exe")
    return out


def _fixed_drive_roots() -> list[Path]:
    """Local disks only. Skip optical drives so the scan does not spin them up."""
    if os.name != "nt":
        return []
    import ctypes

    get_type = ctypes.windll.kernel32.GetDriveTypeW
    roots: list[Path] = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        # 2 removable, 3 fixed. 4 network and 5 cdrom stay out.
        if get_type(root) in (2, 3):
            roots.append(Path(root))
    return roots


def steam_common_dirs() -> list[Path]:
    """steamapps/common at a drive root, a Steam library folder, or one level down."""
    found: list[Path] = []
    seen: set[str] = set()
    for root in _fixed_drive_roots():
        tails = [
            root / "steamapps" / "common",
            root / "Steam" / "steamapps" / "common",
            root / "SteamLibrary" / "steamapps" / "common",
            root / "Program Files (x86)" / "Steam" / "steamapps" / "common",
            root / "Program Files" / "Steam" / "steamapps" / "common",
        ]
        try:
            children = list(root.iterdir())
        except OSError:
            children = []
        for child in children:
            tails.append(child / "steamapps" / "common")
        for common in tails:
            key = str(common).lower()
            if key in seen:
                continue
            seen.add(key)
            if common.is_dir():
                found.append(common)
    return found


def trainzutil_under_common(common: Path) -> Path | None:
    """Folder under steamapps/common whose name contains 'trainz' and has TrainzUtil.exe."""
    if not common.is_dir():
        return None
    hits: list[Path] = []
    try:
        children = list(common.iterdir())
    except OSError:
        return None
    for child in children:
        if not child.is_dir() or "trainz" not in child.name.lower():
            continue
        exe = child / "TrainzUtil.exe"
        if exe.is_file():
            hits.append(exe)
    if not hits:
        return None
    hits.sort(key=lambda exe: (0 if "2022" in exe.parent.name else 1, exe.parent.name.lower()))
    return hits[0]


def trainz_launcher_running() -> bool | None:
    """True/False from the process list. None when the check itself fails."""
    if os.name != "nt":
        return None
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in (proc.stdout or "").splitlines():
        name = line.split(",", 1)[0].strip().strip('"').lower()
        if name.startswith("trainz") or name.startswith("trs"):
            return True
    return False


def collect_script_files(paths: list[Path]) -> list[Path]:
    """`.gs` files from a drop. Folders are scanned in place; nothing is copied."""
    found: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        path = Path(path)
        if path.is_dir():
            candidates = sorted(path.rglob("*.gs"))
        elif path.is_file():
            candidates = [path]
        else:
            continue
        for item in candidates:
            if item.suffix.lower() != ".gs" or not item.is_file():
                continue
            key = str(item.resolve()).casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append(item.resolve())
    return found


def encrypt_batch_body(sources: list[Path]) -> str:
    """One TrainzUtil batch line per script. UTF-8, no BOM, LF."""
    return "".join(f'"encrypt" "{path}"\n' for path in sources)


def encrypt_error_map(text: str) -> dict[str, str]:
    """Path (casefold, backslashes) → first error. Empty string means the command was echoed clean."""
    found: dict[str, str] = {}
    current: str | None = None
    echo = re.compile(r"<NULL>\s*:\s*encrypt\s+\"([^\"]+)\"", re.IGNORECASE)
    for line in text.splitlines():
        if "failure on line" in line.casefold():
            continue
        match = echo.search(line)
        if match:
            current = match.group(1).replace("/", "\\").casefold()
            found.setdefault(current, "")
            continue
        if current is None or found[current]:
            continue
        if "- <NULL>" not in line and not line.strip().startswith("-"):
            continue
        msg = re.split(r"<NULL>\s*:", line, maxsplit=1)[-1].strip()
        if msg:
            found[current] = msg
    return found


def encrypt_scripts(exe: Path, sources: list[Path]) -> list[tuple[Path, bool, str]]:
    """`TrainzUtil encrypt` each `.gs`. The `.gse` is written beside the source."""
    if not sources:
        return []
    started = time.time()
    folder = Path(tempfile.mkdtemp(prefix="mstn-gs-"))
    batch = folder / "encrypt.txt"
    batch.write_bytes(encrypt_batch_body(sources).encode("utf-8"))
    try:
        text = run_trainzutil(exe, [f"@{batch}"], timeout=max(180.0, 20.0 * len(sources)))
    except subprocess.TimeoutExpired:
        return [(src, False, "TrainzUtil timed out") for src in sources]
    except OSError as exc:
        return [(src, False, str(exc)) for src in sources]
    finally:
        batch.unlink(missing_ok=True)
        folder.rmdir()
    errors = encrypt_error_map(text)
    out: list[tuple[Path, bool, str]] = []
    for src in sources:
        dest = src.with_suffix(".gse")
        err = errors.get(str(src).replace("/", "\\").casefold(), "")
        fresh = dest.is_file() and dest.stat().st_mtime >= started - 2
        if err:
            out.append((src, False, err))
        elif fresh:
            out.append((src, True, dest.name))
        else:
            out.append((src, False, "No .gse written"))
    return out


def _encrypt_self_check() -> None:
    body = encrypt_batch_body([Path(r"C:\a b\one.gs"), Path(r"D:\two.gs")])
    assert body == '"encrypt" "C:\\a b\\one.gs"\n"encrypt" "D:\\two.gs"\n'
    log = "\n".join(
        [
            r'  ; <NULL> : encrypt "C:\a b\one.gs"',
            r'  ; <NULL> : encrypt "D:\two.gs"',
            r"    - <NULL> : Invalid input file path: d:/two.gs",
        ]
    )
    errs = encrypt_error_map(log)
    assert errs[r"c:\a b\one.gs"] == ""
    assert "Invalid" in errs[r"d:\two.gs"]
    folder = Path(tempfile.mkdtemp(prefix="mstn-gs-scan-"))
    (folder / "a.gs").write_text("class A {};", encoding="utf-8")
    (folder / "skip.txt").write_text("no", encoding="utf-8")
    nested = folder / "sub"
    nested.mkdir()
    (nested / "b.gs").write_text("class B {};", encoding="utf-8")
    got = collect_script_files([folder, folder / "a.gs", folder / "skip.txt"])
    assert [p.name for p in got] == ["a.gs", "b.gs"]


def run_trainzutil(exe: Path, args: list[str], *, timeout: float = 120) -> str:
    proc = subprocess.run(
        [str(exe), *args],
        cwd=str(exe.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def stream_trainzutil(exe: Path, args: list[str], on_line, *, timeout: float = 180) -> str:
    """Run TrainzUtil and hand each stdout line to on_line as soon as it arrives."""
    proc = subprocess.Popen(
        [str(exe), *args],
        cwd=str(exe.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_CREATE_NO_WINDOW,
    )
    chunks: list[str] = []
    start = time.monotonic()
    assert proc.stdout is not None
    try:
        while True:
            if time.monotonic() - start > timeout:
                proc.kill()
                raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)
            line = proc.stdout.readline()
            if line:
                text = line.rstrip("\r\n")
                chunks.append(text)
                on_line(text)
                continue
            if proc.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.stdout.close()
    return "\n".join(chunks).strip()


def classify_trainz_line(line: str) -> tuple[str, str]:
    """Trainz console tone and the text without the + / - / ! marker.

    error is red, warn is yellow, ok is green, normal is gray.
    """
    raw = line.strip()
    if not raw:
        return "normal", ""
    sign = ""
    body = raw
    if "<NULL>" in raw:
        head, body = re.split(r"<NULL>\s*:", raw, maxsplit=1)
        body = body.strip()
        mark = head.strip()
        if mark.endswith("-") or mark.startswith("-"):
            sign = "-"
        elif mark.endswith("+") or mark.startswith("+"):
            sign = "+"
        elif "!" in mark:
            sign = "!"
    elif raw[:1] in "+-!":
        sign = raw[0]
        body = raw[1:].strip()
    low = body.lower()
    if low.startswith("ok ("):
        errors = re.search(r"(\d+)\s+errors", low)
        warnings = re.search(r"(\d+)\s+warnings", low)
        if errors and int(errors.group(1)) > 0:
            return "error", body
        if warnings and int(warnings.group(1)) > 0:
            return "warn", body
        return "ok", body
    if sign == "-":
        return "error", body or raw
    if sign == "!":
        return "warn", body or raw
    if sign == "+":
        return "ok", body or raw
    if "warning" in low and "0 warning" not in low:
        return "warn", body or raw
    if re.search(r"\berror\b", low) and "0 error" not in low:
        return "error", body or raw
    return "normal", body or raw


def classify_trainz_log(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        tone, shown = classify_trainz_line(line)
        if shown:
            rows.append({"text": shown, "tone": tone})
    return rows


def probe_launcher(exe: Path) -> tuple[bool, str]:
    """Version plus a database command. Debug tools off looks like 'not running'."""
    running = trainz_launcher_running()
    if running is False:
        return False, "Open the Trainz Launcher first"
    try:
        version = run_trainzutil(exe, ["version"], timeout=20)
    except subprocess.TimeoutExpired:
        return False, "TrainzUtil timed out"
    except OSError as exc:
        return False, str(exc)
    if launcher_blocked(version):
        return False, "Open the Trainz Launcher first"
    try:
        db = run_trainzutil(exe, ["authors"], timeout=30)
    except subprocess.TimeoutExpired:
        return False, "Launcher did not answer — turn on Advanced debug tools"
    if launcher_blocked(db):
        return False, "Launcher is open but Advanced debug tools are off"
    build = "Connected"
    for line in version.splitlines():
        body = re.split(r"<NULL>\s*:", line, maxsplit=1)[-1].strip()
        if body and "version" not in body.lower() and "null" not in body.lower():
            build = body
            break
    return True, build


def decode_status(raw: str) -> str:
    """Turn a status flag token into short phrases. Unknown letters stay as-is."""
    known = set("ABCDEFGILMOPUXY")
    flags = ""
    for part in raw.replace("\n", " ").split(":"):
        letters = "".join(ch for ch in part.strip() if ch.isalpha())
        if len(letters) >= 4 and all(ch.upper() in known for ch in letters):
            flags = letters
            break
    if not flags:
        return raw.strip()[:500] or "No status"
    names = {
        "A": "archived",
        "B": "builtin",
        "C": "base content",
        "D": "on Download Station",
        "E": "open for edit",
        "F": "faulty",
        "G": "game component",
        "I": "installed",
        "L": "modified locally",
        "M": "missing dependencies",
        "O": "obsolete",
        "P": "payware",
        "U": "update available",
        "X": "authorised",
        "Y": "compatible",
    }
    on = [names[ch] for ch in flags if ch.isupper() and ch in names]
    if "I" not in flags:
        on.insert(0, "not installed")
    return ", ".join(on) if on else flags


_LIBRARY_LINE = re.compile(
    r"[+-]\s*(<kuid2?:-?\d+:-?\d+(?::-?\d+)?>)\s*:\s*([A-Za-z]+)\s*:\s*(.*?)\s*:\s*(.*)$"
)


@dataclass(frozen=True)
class LibraryAsset:
    kuid: str
    name: str
    flags: str
    category: str
    faulty: bool


def category_is_enginespec(category: str) -> bool:
    """TrainzUtil status category token for an engine-spec asset."""
    return "ESPC" in {part.strip().upper() for part in category.split(";") if part.strip()}


_INSTALL_DATA_RE = re.compile(r"^\s*\+\s*<NULL>\s*:\s*(.+?)\s*$", re.MULTILINE)


def parse_installation_data_path(text: str) -> Path | None:
    """Path from `TrainzUtil getinstallationdatapath`. The drive letter keeps its colon."""
    match = _INSTALL_DATA_RE.search(text or "")
    if match is None:
        return None
    raw = match.group(1).strip().strip('"')
    if not raw or "<" in raw:
        return None
    return Path(raw)


def installation_data_path(exe: Path) -> Path | None:
    """Local data folder for this TrainzUtil install. Empty when the reply is not a folder."""
    found = parse_installation_data_path(
        run_trainzutil(exe, ["getinstallationdatapath"], timeout=30)
    )
    if found is None or not found.is_dir():
        return None
    return found


def _n3v_builds() -> list[Path]:
    """Build folders under Local AppData. Used only when getinstallationdatapath is unavailable."""
    local = os.environ.get("LOCALAPPDATA", "")
    root = Path(local) / "N3V Games" if local else None
    if root is None or not root.is_dir():
        return []
    found: list[Path] = []
    for build in root.glob("*/build *"):
        if (build / "local").is_dir() or (build / "original").is_dir() or (build / "editing").is_dir():
            found.append(build)
    return found


def trainz_data_dir() -> Path | None:
    """Workspace content root. local/ and original/ already live here — do not walk AppData."""
    from trainz_studio import REPO_ROOT

    if (REPO_ROOT / "local").is_dir() or (REPO_ROOT / "original").is_dir():
        return REPO_ROOT
    return None


def trainz_editing_dir(data_dir: Path | None = None) -> Path | None:
    """Open-for-edit assets. Prefer `<installation data>/editing` from TrainzUtil."""
    if data_dir is not None:
        editing = data_dir / "editing"
        if editing.is_dir():
            return editing
    local = os.environ.get("LOCALAPPDATA", "")
    root = Path(local) / "N3V Games" if local else None
    if root is None or not root.is_dir():
        return None
    found: list[Path] = []
    for editing in root.glob("*/build */editing"):
        if editing.is_dir():
            found.append(editing)
    for editing in found:
        if "trs22" in str(editing).lower():
            return editing
    return found[0] if found else None


def config_in_editing(editing: Path, kuid: str) -> Path | None:
    token = kuid.strip()
    if not token or not editing.is_dir():
        return None
    for child in editing.iterdir():
        cfg = child / "config.txt"
        if not cfg.is_file():
            continue
        try:
            body = cfg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if token in body:
            return cfg
    return None


_COVER_NAMES = (
    "$screenshot$.jpg",
    "$screenshot$.jpeg",
    "$screenshot$.png",
    "thumbnail.jpg",
    "thumbnail.jpeg",
    "thumbnail.png",
    "thumb.jpg",
    "thumb.png",
    "screenshot.jpg",
    "preview.jpg",
)
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tga", ".bmp", ".webp"}


def thumbnail_image_names(raw: bytes) -> list[str]:
    """Image paths from the config `thumbnails` container. Root tags only."""
    if not raw:
        return []
    if raw[:4] == b"ACS$":
        return _chump_thumbnail_images(raw)
    from .cdp_lzss import decode_asset_text

    return _text_thumbnail_images(decode_asset_text(raw))


def _text_thumbnail_images(text: str) -> list[str]:
    start = re.search(r"(?im)^\s*thumbnails\s*\{", text)
    if start is None:
        return []
    depth = 0
    body: list[str] = []
    for ch in text[start.end() - 1 :]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body.append(ch)
                break
        body.append(ch)
    return [match.group(1).strip() for match in re.finditer(r'(?im)\bimage\s+"([^"]+)"', "".join(body))]


def _chump_pairs(blob: bytes):
    pos = 0
    end = len(blob)
    while pos + 5 <= end:
        pair_len = struct.unpack_from("<I", blob, pos)[0]
        if pair_len < 2 or pos + 4 + pair_len > end:
            return
        pair_end = pos + 4 + pair_len
        name_size = blob[pos + 4]
        name_at = pos + 5
        if name_size < 1 or name_at + name_size > pair_end:
            return
        name = blob[name_at : name_at + name_size - 1].decode("utf-8", errors="replace")
        type_at = name_at + name_size
        if type_at >= pair_end:
            return
        yield name, blob[type_at], blob[type_at + 1 : pair_end]
        pos = pair_end


def _chump_image(payload: bytes) -> str:
    return payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip().strip('"')


def _chump_thumbnail_images(raw: bytes) -> list[str]:
    if len(raw) < 16:
        return []
    length = struct.unpack_from("<I", raw, 12)[0]
    names: list[str] = []
    for name, kind, payload in _chump_pairs(raw[16 : 16 + length]):
        if name.lower() != "thumbnails" or kind != 0:
            continue
        for inner_name, inner_kind, inner in _chump_pairs(payload):
            if inner_kind == 0:
                for leaf_name, leaf_kind, leaf in _chump_pairs(inner):
                    if leaf_name.lower() == "image" and leaf_kind == 3:
                        text = _chump_image(leaf)
                        if text:
                            names.append(text)
            elif inner_name.lower() == "image" and inner_kind == 3:
                text = _chump_image(inner)
                if text:
                    names.append(text)
    return names


def _cover_names(raw: bytes) -> tuple[str, ...]:
    ordered: list[str] = []
    for name in thumbnail_image_names(raw):
        if name not in ordered:
            ordered.append(name)
        stem = Path(name.replace("\\", "/")).stem
        if Path(name).suffix.lower() == ".texture":
            for ext in (".jpg", ".png", ".tga"):
                alt = f"{stem}{ext}"
                if alt not in ordered:
                    ordered.append(alt)
    for name in _COVER_NAMES:
        if name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def _image_suffix(blob: bytes, hint: str) -> str:
    if blob.startswith(b"\xff\xd8"):
        return ".jpg"
    if blob.startswith(b"\x89PNG"):
        return ".png"
    if blob.startswith(b"GIF8"):
        return ".gif"
    suffix = Path(hint).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in _IMAGE_SUFFIXES:
        return suffix
    return ".jpg"


def cover_in_folder(folder: Path) -> Path | None:
    """Asset cover sitting loose in an open editing folder."""
    names: list[str] = []
    config = folder / "config.txt"
    if config.is_file():
        try:
            names = list(thumbnail_image_names(config.read_bytes()))
        except OSError:
            names = []
    wanted = [name.replace("\\", "/") for name in (*names, *_COVER_NAMES)]
    bases = {Path(name).name.casefold() for name in wanted}
    for name in wanted:
        direct = folder.joinpath(*name.split("/"))
        if direct.is_file():
            return direct
    try:
        for path in folder.rglob("*"):
            if path.is_file() and path.name.casefold() in bases and path.suffix.lower() in _IMAGE_SUFFIXES:
                return path
    except OSError:
        return None
    return None


def asset_browse_dir(data_dir: Path, kuid: str, archives: dict[str, Path] | None = None) -> Path | None:
    """Folder the Packages finder can walk.

    The open edit wins. Otherwise the tzarc is unpacked once into the user cache,
    keyed by archive mtime, and that folder is returned.
    """
    editing = data_dir / "editing"
    if editing.is_dir():
        folder = editing_folder_for(editing, kuid)
        if folder is not None and folder.is_dir():
            return folder
    index = archives if archives is not None else archive_index(data_dir)
    archive = index.get(kuid)
    if archive is None or not archive.is_file():
        return None
    return _cached_tzarc_unpack(archive, kuid)


def _cached_tzarc_unpack(archive: Path, kuid: str) -> Path | None:
    safe = re.sub(r"[^0-9A-Za-z]+", "_", kuid).strip("_") or "asset"
    cache = Path.home() / ".cache" / "trainz_studio" / "unpack" / safe
    stamp = cache / ".stamp"
    try:
        stat = archive.stat()
    except OSError:
        return None
    key = f"{archive}:{int(stat.st_mtime)}:{stat.st_size}"
    try:
        if stamp.is_file() and stamp.read_text(encoding="utf-8") == key:
            if any(path.name != ".stamp" for path in cache.iterdir()):
                return cache
    except OSError:
        return None
    from .tzarc import extract_tzarc

    try:
        cache.mkdir(parents=True, exist_ok=True)
        extract_tzarc(archive, cache)
        stamp.write_text(key, encoding="utf-8")
    except (OSError, ValueError):
        return None
    return cache


def editing_index(editing: Path) -> dict[str, Path]:
    """KUID → open editing folder. The folder's own `kuid` tag, not a dependency."""
    found: dict[str, Path] = {}
    if not editing.is_dir():
        return found
    own = re.compile(r"(?im)^\s*kuid\s+(<kuid2?:-?\d+:-?\d+(?::-?\d+)?>)")
    try:
        children = list(editing.iterdir())
    except OSError:
        return found
    for child in children:
        if not child.is_dir():
            continue
        named = kuid_from_archive_name(child.name)
        if named:
            found[named] = child
            continue
        config = child / "config.txt"
        if not config.is_file():
            continue
        try:
            text = config.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = own.search(text)
        if match is not None:
            found.setdefault(match.group(1), child)
    return found


def editing_folder_for(editing: Path, kuid: str) -> Path | None:
    if not editing.is_dir():
        return None
    try:
        children = list(editing.iterdir())
    except OSError:
        return None
    for child in children:
        if child.is_dir() and kuid_from_archive_name(child.name) == kuid:
            return child
    config = config_in_editing(editing, kuid)
    return config.parent if config is not None else None


def archive_index(data_dir: Path) -> dict[str, Path]:
    """KUID → tzarc. `local` wins over `original`. Filenames only, archives stay closed."""
    chosen: dict[str, Path] = {}
    for folder_name in ("original", "local"):
        folder = data_dir / folder_name
        if not folder.is_dir():
            continue
        try:
            buckets = list(folder.iterdir())
        except OSError:
            continue
        for bucket in buckets:
            if not bucket.is_dir():
                continue
            try:
                names = list(bucket.iterdir())
            except OSError:
                continue
            for path in names:
                if not path.is_file() or path.suffix.lower() != ".tzarc":
                    continue
                kuid = kuid_from_archive_name(path.name)
                if kuid is not None:
                    chosen[kuid] = path
    return chosen


def asset_cover_path(
    data_dir: Path,
    kuid: str,
    archives: dict[str, Path] | None = None,
    editing_folders: dict[str, Path] | None = None,
) -> Path | None:
    """Cover from the config `thumbnails` image, then the usual screenshot names.

    A loose file in the editing folder wins. Otherwise the named file is read out
    of the tzarc and cached by archive mtime.
    """
    folders = editing_folders if editing_folders is not None else editing_index(data_dir / "editing")
    folder = folders.get(kuid)
    if folder is not None:
        loose = cover_in_folder(folder)
        if loose is not None:
            return loose
    index = archives if archives is not None else archive_index(data_dir)
    archive = index.get(kuid)
    if archive is None or not archive.is_file():
        return None
    from .tzarc import read_tzarc_config, read_tzarc_named

    try:
        names = _cover_names(read_tzarc_config(archive))
        blob = read_tzarc_named(archive, names)
    except (OSError, ValueError):
        return None
    if len(blob) < 32:
        return None
    safe = re.sub(r"[^0-9A-Za-z]+", "_", kuid).strip("_") or "asset"
    cache = Path.home() / ".cache" / "trainz_studio" / "covers"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"{safe}{_image_suffix(blob, names[0] if names else '')}"
    stamp = cache / f"{safe}.stamp"
    try:
        stat = archive.stat()
        key = f"{archive}:{int(stat.st_mtime)}:{stat.st_size}:{dest.name}"
        if dest.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == key:
            return dest
        dest.write_bytes(blob)
        stamp.write_text(key, encoding="utf-8")
    except OSError:
        return None
    return dest


def commit_enginespec(exe: Path, kuid: str, text: str) -> str:
    """Open the asset for edit, replace config.txt, and commit it back into the game."""
    try:
        data_dir = installation_data_path(exe)
    except (OSError, subprocess.TimeoutExpired):
        data_dir = None
    editing = trainz_editing_dir(data_dir)
    if editing is None:
        raise RuntimeError("Trainz editing folder was not found")
    opened = run_trainzutil(exe, ["edit", kuid], timeout=120)
    if launcher_blocked(opened):
        raise RuntimeError("Open the Trainz Launcher first")
    path = config_in_editing(editing, kuid)
    if path is None:
        detail = tidy_trainzutil(opened)
        raise RuntimeError(detail or "Trainz did not open an editing folder for this asset")
    body = text if text.endswith("\n") else text + "\n"
    path.write_text(body, encoding="utf-8", newline="\n")
    committed = run_trainzutil(exe, ["commit", kuid], timeout=180)
    if launcher_blocked(committed):
        raise RuntimeError("Open the Trainz Launcher first")
    detail = tidy_trainzutil(committed)
    lowered = detail.lower()
    if "error" in lowered and "0 errors" not in lowered:
        raise RuntimeError(detail or "Commit failed")
    return detail or "Committed"


_TZARC_NAME = re.compile(r"^(kuid2|kuid)\s+(-?\d+)\s+(-?\d+)(?:\s+(-?\d+))?\.tzarc$", re.IGNORECASE)
_EDIT_DIR = re.compile(r"^(kuid2|kuid)\s+(-?\d+)\s+(-?\d+)(?:\s+(-?\d+))?(?:\s|$)", re.IGNORECASE)


_KUID_TOKEN = re.compile(r"<kuid2?:-?\d+:-?\d+(?::-?\d+)?>")


def dependency_kuids(text: str, *, skip: str = "") -> list[str]:
    """KUID tokens from a list-dependencies printout, without the asset itself."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _KUID_TOKEN.finditer(text):
        kuid = match.group(0)
        if kuid == skip or kuid in seen:
            continue
        seen.add(kuid)
        found.append(kuid)
    return found


def kuid_from_archive_name(name: str) -> str | None:
    """`kuid 1144998 100169.tzarc` or `kuid2 124060 21035 3.tzarc` → a KUID token."""
    match = _TZARC_NAME.match(name.strip())
    if match is None:
        match = _EDIT_DIR.match(name.strip())
    if match is None:
        return None
    kind, user, content, version = match.groups()
    if kind.lower() == "kuid2":
        return f"<kuid2:{user}:{content}:{version or 0}>"
    return f"<kuid:{user}:{content}>"


_DAY_DIR = re.compile(r"^(\d{2})-(\d{2})-(\d{2})$")
_BACKUP_HEAD = re.compile(
    r"^(kuid2|kuid)\s+(-?\d+)\s+(-?\d+)(?:\s+(-?\d+))?",
    re.IGNORECASE,
)
_SEARCH_TOKEN = re.compile(r"[0-9A-Za-z]+")
_HASH_DIR = re.compile(r"^[a-z0-9]{6,16}$")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class AssetBackup:
    day: str
    day_key: str
    name: str
    kind: str
    path: str
    size: int
    mtime: float
    kuid: str
    when: str


def backup_kuid(name: str) -> str:
    """Backup folder or `*.tzarc_<hash>` stem → a KUID token. Empty when the name is not an asset."""
    match = _BACKUP_HEAD.match(name.strip())
    if match is None:
        return ""
    kind, user, content, version = match.groups()
    if kind.lower() == "kuid2":
        return f"<kuid2:{user}:{content}:{version or 0}>"
    return f"<kuid:{user}:{content}>"


def _search_tokens(text: str) -> list[str]:
    """Name words and KUID digits. A short number still matches, so `10007` hits `100079`."""
    skip = {"kuid", "kuid2"}
    return [
        part.casefold()
        for part in _SEARCH_TOKEN.findall(text)
        if len(part) >= 2 and part.casefold() not in skip
    ]


def _day_label(name: str) -> str:
    match = _DAY_DIR.match(name)
    if match is None:
        return name
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12:
        return name
    return f"{day} {_MONTHS[month - 1]} 20{year:02d}"


def find_asset_backups(data_dir: Path, query: str, *, limit: int = 2000) -> list[AssetBackup]:
    """Copies under `<data>/backups/<yy-mm-dd>/`.

    Every word or number in the query must appear in the backup name, so a partial
    KUID such as `10007` matches `100079`. An empty query lists the asset copies.
    Date folders only — hash route folders stay out.
    """
    needle = query.strip()
    folder = data_dir / "backups"
    if not folder.is_dir():
        return []
    tokens = _search_tokens(needle)
    found: list[AssetBackup] = []
    try:
        days = [day for day in folder.iterdir() if day.is_dir() and _DAY_DIR.match(day.name)]
    except OSError:
        return []
    for day in days:
        try:
            children = list(day.iterdir())
        except OSError:
            continue
        label = _day_label(day.name)
        for child in children:
            name = child.name
            kuid = backup_kuid(name)
            blob = name.casefold()
            if tokens and not all(token in blob for token in tokens):
                continue
            if not tokens and not kuid and ".tzarc" not in blob and _HASH_DIR.match(name):
                continue
            try:
                stat = child.stat()
            except OSError:
                continue
            lowered = name.casefold()
            if child.is_dir():
                kind = "Folder"
                size = 0
            elif ".tzarc" in lowered:
                kind = "tzarc"
                size = stat.st_size
            else:
                kind = "File"
                size = stat.st_size
            found.append(
                AssetBackup(
                    day=label,
                    day_key=day.name,
                    name=name,
                    kind=kind,
                    path=str(child),
                    size=size,
                    mtime=stat.st_mtime,
                    kuid=kuid,
                    when=time.strftime("%H:%M", time.localtime(stat.st_mtime)),
                )
            )
    found.sort(key=lambda row: (row.day_key, row.mtime), reverse=True)
    return found[:limit]


_KIND_TAG = re.compile(r'(?im)^kind\s+"?([^"\r\n]+)"?')
_NAME_TAG = re.compile(r'(?im)^username\s+"?([^"\r\n]+)"?')
_TAIL_HASH = re.compile(r"_\d{6,}$")


def backup_display_name(name: str) -> str:
    stem = re.sub(r"\.tzarc.*$", "", name, count=1, flags=re.IGNORECASE)
    return _TAIL_HASH.sub("", stem).strip() or name


def _backup_config(path: Path) -> str:
    if path.is_dir():
        cfg = path / "config.txt"
        if not cfg.is_file():
            return ""
        try:
            return cfg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    if ".tzarc" not in path.name.casefold():
        return ""
    try:
        from .tzarc import read_tzarc_config

        return read_tzarc_config(path).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def describe_backup(path: Path) -> dict[str, str]:
    """Fields for the sidebar card of one backup copy."""
    stat = path.stat()
    name = path.name
    kuid = backup_kuid(name)
    copy_kind = "Folder" if path.is_dir() else ("tzarc" if ".tzarc" in name.casefold() else "File")
    text = _backup_config(path)
    author, build = author_and_build(text) if text else ("", "")
    asset_kind = ""
    username = ""
    if text:
        kind_match = _KIND_TAG.search(text)
        name_match = _NAME_TAG.search(text)
        if kind_match is not None:
            asset_kind = kind_match.group(1).strip().strip('"')
        if name_match is not None:
            username = name_match.group(1).strip().strip('"')
    parent = path.parent.name
    day = _day_label(parent) if _DAY_DIR.match(parent) else parent
    return {
        "kuid": kuid,
        "title": username or backup_display_name(name),
        "category": asset_kind or copy_kind,
        "installed": day,
        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
        "size": format_bytes(stat.st_size) if path.is_file() else "Folder",
        "author": author,
        "build": build,
        "note": str(path),
        "status": copy_kind,
    }


def _read_cores(jobs: int) -> int:
    """Every logical processor. scandir, stat, and zlib release the GIL, so the pool is real cores."""
    from ..util.hw import cpu_count

    if jobs <= 1:
        return 1
    return min(jobs, cpu_count())


class _Arch(tuple):
    """path, mtime, mtime_ns, size. A tuple so workers can hand it back cheaply."""

    __slots__ = ()

    @property
    def path(self) -> Path:
        return self[0]

    @property
    def mtime(self) -> float:
        return self[1]

    @property
    def mtime_ns(self) -> int:
        return self[2]

    @property
    def size(self) -> int:
        return self[3]


def _scan_tzarc_bucket(bucket: str) -> dict[str, _Arch]:
    found: dict[str, _Arch] = {}
    try:
        with os.scandir(bucket) as it:
            for entry in it:
                name = entry.name
                if len(name) < 7 or not name.lower().endswith(".tzarc"):
                    continue
                kuid = kuid_from_archive_name(name)
                if kuid is None:
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                found[kuid] = _Arch((Path(entry.path), st.st_mtime, st.st_mtime_ns, st.st_size))
    except OSError:
        return {}
    return found


def _scan_archive_folder(folder: Path) -> dict[str, _Arch]:
    if not folder.is_dir():
        return {}
    try:
        buckets = [entry.path for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return {}
    found: dict[str, _Arch] = {}
    if not buckets:
        return found
    cores = _read_cores(len(buckets))
    if cores == 1:
        parts = [_scan_tzarc_bucket(bucket) for bucket in buckets]
    else:
        with ThreadPoolExecutor(max_workers=cores) as pool:
            parts = list(pool.map(_scan_tzarc_bucket, buckets))
    for part in parts:
        found.update(part)
    return found


def _scan_editing_child(path: str) -> tuple[str, float, str] | None:
    kuid = kuid_from_archive_name(Path(path).name)
    if kuid is None:
        return None
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return None
    config = os.path.join(path, "config.txt")
    if not os.path.isfile(config):
        config = ""
    return kuid, mtime, config


def _scan_editing(folder: Path) -> tuple[dict[str, float], dict[str, Path]]:
    mtimes: dict[str, float] = {}
    configs: dict[str, Path] = {}
    if not folder.is_dir():
        return mtimes, configs
    try:
        kids = [entry.path for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return mtimes, configs
    if not kids:
        return mtimes, configs
    cores = _read_cores(len(kids))
    if cores == 1:
        rows = [_scan_editing_child(kid) for kid in kids]
    else:
        with ThreadPoolExecutor(max_workers=cores) as pool:
            rows = list(pool.map(_scan_editing_child, kids))
    for row in rows:
        if row is None:
            continue
        kuid, mtime, config = row
        mtimes[kuid] = mtime
        if config:
            configs[kuid] = Path(config)
    return mtimes, configs


class ContentIndex:
    """One parallel listing of original, local, and editing. Dates and authors share it."""

    __slots__ = ("original", "local", "editing_mtime", "editing_config")

    def __init__(
        self,
        original: dict[str, _Arch],
        local: dict[str, _Arch],
        editing_mtime: dict[str, float],
        editing_config: dict[str, Path],
    ) -> None:
        self.original = original
        self.local = local
        self.editing_mtime = editing_mtime
        self.editing_config = editing_config

    def chosen(self) -> dict[str, _Arch]:
        """Local archive wins over the original copy of the same KUID."""
        found = dict(self.original)
        found.update(self.local)
        return found


def index_content(roots: list[Path] | None = None) -> ContentIndex:
    """List tzarc files on every logical core. One pass feeds dates and the author cache."""
    original: dict[str, _Arch] = {}
    local: dict[str, _Arch] = {}
    editing_mtime: dict[str, float] = {}
    editing_config: dict[str, Path] = {}
    for base in roots if roots is not None else content_roots():
        original.update(_scan_archive_folder(base / "original"))
        local.update(_scan_archive_folder(base / "local"))
        times, configs = _scan_editing(base / "editing")
        editing_mtime.update(times)
        editing_config.update(configs)
    return ContentIndex(original, local, editing_mtime, editing_config)


def _archive_mtimes(folder: Path) -> tuple[dict[str, float], dict[str, int]]:
    found = _scan_archive_folder(folder)
    return (
        {kuid: arch.mtime for kuid, arch in found.items()},
        {kuid: arch.size for kuid, arch in found.items()},
    )


def _editing_mtimes(folder: Path) -> dict[str, float]:
    times, _configs = _scan_editing(folder)
    return times


def content_roots() -> list[Path]:
    """Repo `local`/`original`, then any N3V build folder that has the same layout."""
    from trainz_studio import REPO_ROOT

    roots: list[Path] = []
    if (REPO_ROOT / "local").is_dir() or (REPO_ROOT / "original").is_dir():
        roots.append(REPO_ROOT)
    roots.extend(_n3v_builds())
    return roots


def read_asset_dates(
    roots: list[Path] | None = None,
    index: ContentIndex | None = None,
) -> dict[str, dict[str, float]]:
    """File times from original (installed) and local (modified), plus archive byte sizes."""
    if index is None:
        index = index_content(roots)
    installed = {kuid: arch.mtime for kuid, arch in index.original.items()}
    modified = {kuid: arch.mtime for kuid, arch in index.local.items()}
    sizes = {kuid: arch.size for kuid, arch in index.original.items()}
    sizes.update({kuid: arch.size for kuid, arch in index.local.items()})
    return {
        "installed": installed,
        "modified": modified,
        "editing": dict(index.editing_mtime),
        "sizes": sizes,
    }


def status_bits(flags: str, *, open_for_edit: bool = False, locally_modified: bool = False) -> list[str]:
    bits: list[str] = []
    if open_for_edit or "E" in flags:
        bits.append("Edit")
    if "F" in flags:
        bits.append("Faulty")
    if "M" in flags:
        bits.append("Missing")
    if locally_modified or "L" in flags:
        bits.append("Modified")
    if "O" in flags:
        bits.append("Obsolete")
    if "U" in flags:
        bits.append("Update")
    return bits or ["Installed"]


def status_rank(bits: list[str]) -> int:
    order = ("Edit", "Faulty", "Missing", "Modified", "Obsolete", "Update", "Installed")
    for index, name in enumerate(order):
        if name in bits:
            return index
    return len(order)


def parse_installed_library(text: str) -> list[LibraryAsset]:
    """Lines from ``filterbystatus I``. Capital F is faulty. Uninstalled rows drop out."""
    found: dict[str, LibraryAsset] = {}
    for line in text.splitlines():
        match = _LIBRARY_LINE.search(line)
        if match is None:
            continue
        kuid, flags, category, name = match.groups()
        if "I" not in flags:
            continue
        found[kuid] = LibraryAsset(
            kuid=kuid,
            name=(name or kuid).strip() or kuid,
            flags=flags,
            category=category.strip(),
            faulty="F" in flags,
        )
    rows = list(found.values())
    rows.sort(key=lambda row: (not row.faulty, row.name.casefold()))
    return rows


def load_installed_library(exe: Path) -> tuple[list[LibraryAsset], str]:
    """Installed assets only. One batch: local list, then keep flag I. Needs the Launcher."""
    batch = Path(tempfile.gettempdir()) / "mstn-tu-library.txt"
    batch.write_text(
        "\n".join(
            [
                '"set" "all" "searchbycategory" "-"',
                '"set" "inst" "filterbystatus" "I" $(all)',
                '"print" "inst"',
            ]
        ),
        encoding="utf-8",
    )
    try:
        text = run_trainzutil(exe, ["@" + str(batch)], timeout=180)
    except subprocess.TimeoutExpired:
        return [], "Content Manager took too long"
    except OSError as exc:
        return [], str(exc)
    if launcher_blocked(text):
        return [], "Open the Trainz Launcher first"
    rows = parse_installed_library(text)
    if not rows and "error" in text.lower():
        return [], text.strip()[-300:] or "Library read failed"
    return rows, ""


def library_cache_file(exe: Path, *, root: Path | None = None) -> Path:
    key = hashlib.sha1(str(Path(exe).resolve()).casefold().encode()).hexdigest()[:16]
    base = root if root is not None else Path.home() / ".cache" / "trainz_studio"
    return base / f"tu-library-{key}.json"


def write_library_cache(exe: Path, rows: list[LibraryAsset], *, root: Path | None = None) -> None:
    """Disk copy so the next open paints the library before TrainzUtil answers."""
    path = library_cache_file(exe, root=root)
    payload = [
        {
            "kuid": row.kuid,
            "name": row.name,
            "flags": row.flags,
            "category": row.category,
            "faulty": row.faulty,
        }
        for row in rows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_library_cache(exe: Path, *, root: Path | None = None) -> list[LibraryAsset]:
    path = library_cache_file(exe, root=root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []
    if not isinstance(raw, list):
        return []
    rows: list[LibraryAsset] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kuid = str(item.get("kuid") or "")
        if not kuid:
            continue
        rows.append(
            LibraryAsset(
                kuid=kuid,
                name=str(item.get("name") or kuid),
                flags=str(item.get("flags") or ""),
                category=str(item.get("category") or ""),
                faulty=bool(item.get("faulty")),
            )
        )
    return rows


_CREDIT_TAG = re.compile(
    r"(author|organisation|trainz-build)\s+(.+)$",
    re.IGNORECASE,
)


def _credit_fields(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        body = re.split(r"<NULL>\s*:", line, maxsplit=1)[-1].strip()
        match = _CREDIT_TAG.match(body)
        if match is None:
            continue
        found[match.group(1).lower()] = match.group(2).strip().strip('"')
    return found


def config_credits(text: str) -> str:
    """Author, organisation, and trainz-build from one printconfig dump.

    Install and modified dates are not in this dump.
    """
    found = _credit_fields(text)
    return " · ".join(
        found[key] for key in ("author", "organisation", "trainz-build") if found.get(key)
    )


def author_and_build(text: str) -> tuple[str, str]:
    found = _credit_fields(text)
    return found.get("author", ""), found.get("trainz-build", "")


def author_label(author: str, build: str = "") -> str:
    """Name for the Author column. A bare trainz-build like 3.7 is not a name."""
    author = author.strip()
    build = build.strip()
    if not author:
        return ""
    if build and author == build:
        return ""
    if re.fullmatch(r"\d+\.\d+", author):
        return ""
    return author


def _fmt_chump_float(value: float) -> str:
    text = f"{value:g}"
    if "." not in text and "e" not in text.lower():
        text += ".0"
    return text


_CONFIG_TAGS = ("author", "trainz-build", "username")


def config_identity(raw: bytes) -> tuple[str, str, str]:
    """Author, trainz-build, and username from config.txt or config.chump.

    Root tags only. Soup bodies are skipped, so a route config is not walked.
    Text is UTF-8, UTF-16, or CP932. TrainzUtil's own print replaces Japanese
    with ``?`` on a non-Japanese ANSI code page, so the file is the source.
    """
    if not raw:
        return "", "", ""
    if raw[:4] != b"ACS$":
        from .cdp_lzss import decode_asset_text

        text = decode_asset_text(raw)
        author, build = author_and_build(text)
        match = _NAME_TAG.search(text)
        username = match.group(1).strip().strip('"') if match else ""
        return author, build, username
    if len(raw) < 16:
        return "", "", ""
    length = struct.unpack_from("<I", raw, 12)[0]
    pos = 16
    end = min(16 + length, len(raw))
    found: dict[str, str] = {}
    while pos + 5 <= end and len(found) < len(_CONFIG_TAGS):
        pair_len = struct.unpack_from("<I", raw, pos)[0]
        pair_end = min(pos + 4 + pair_len, end)
        name_size = raw[pos + 4]
        name_at = pos + 5
        if name_size < 1 or name_at + name_size > pair_end:
            break
        name = raw[name_at : name_at + name_size - 1].decode("utf-8", errors="replace").lower()
        type_at = name_at + name_size
        if name in _CONFIG_TAGS and type_at < pair_end:
            kind = raw[type_at]
            payload = raw[type_at + 1 : pair_end]
            if kind == 3:
                found[name] = payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip().strip('"')
            elif kind == 1 and len(payload) >= 4:
                count = len(payload) - (len(payload) % 4)
                found[name] = ",".join(str(struct.unpack_from("<i", payload, i)[0]) for i in range(0, count, 4))
            elif kind == 2 and len(payload) >= 4:
                found[name] = _fmt_chump_float(struct.unpack_from("<f", payload)[0])
        pos = pair_end if pair_end > pos else end
    return found.get("author", ""), found.get("trainz-build", ""), found.get("username", "")


def credit_from_config_bytes(raw: bytes) -> tuple[str, str]:
    """Author and trainz-build. See ``config_identity``."""
    author, build, _username = config_identity(raw)
    return author, build


# Category-list tokens from TrainzUtil → the words Find and the Type column use.
# A code that is not in this map stays as written. Parents that sit on almost
# every row (scenery, train, component) drop out when a more specific token remains.
_CATEGORY_GENERIC = frozenset({"SY", "SCEN", "TR", "TV", "CMP"})
_CATEGORY_NAMES = {
    "?ENV": "Environment",
    "?EW": "Water",
    "?WA": "Signal",
    "?WM": "Trackmark",
    "?WS": "Sign",
    "?WT": "Trigger",
    "?WX": "Junction",
    "#CCARLIB": "Library",
    "#CCARSCENERY": "Scenery",
    "#CCARVEHICLE": "Vehicle",
    "#ENGINESPEC": "Engine Spec",
    "#FXCLT": "Clutter",
    "#HOUSES": "Houses",
    "ACC": "Roadside",
    "ACHC": "Achievement Category",
    "ACHG": "Achievement Group",
    "ACT": "Activity",
    "ACTV": "Active",
    "AGRP": "Asset Group",
    "AIR": "Aircraft",
    "ANTX": "Livestock",
    "AQUA": "Water",
    "AU": "Australia",
    "BD": "Building",
    "BDB": "Buildable",
    "BKL": "Bulk",
    "BLD": "Building",
    "BOG": "Bogey",
    "BOGEY": "Bogey",
    "BOGY": "Bogey",
    "BR": "Bridge",
    "BRDG": "Bridge",
    "BRG": "Bridge",
    "BRIDGE": "Bridge",
    "BRSH": "Ground Brush",
    "CA": "Canada",
    "CAB": "Caboose",
    "CLUT": "Clutter",
    "CMP": "Component",
    "CN": "Consist",
    "COM": "Commercial",
    "CON": "Container",
    "CONT": "Container",
    "CROS": "Crossing",
    "CS": "Control Set",
    "CY": "Commodity",
    "DE": "Germany",
    "DIES": "Diesel",
    "DR": "Driver",
    "ELEC": "Electric",
    "ENG": "Engine",
    "ENV": "Environment",
    "ESND": "Engine Sound",
    "ESPC": "Engine Spec",
    "EU": "Europe",
    "FA": "Fauna",
    "FIXD": "Fixed Track",
    "FL": "Flora",
    "FLAT": "Flatcar",
    "FNC": "Fence",
    "FR": "France",
    "FRT": "Freight",
    "FXP": "Effect",
    "GEN": "General",
    "GMNU": "Gameplay Menu",
    "GRND": "Ground",
    "GRSS": "Grass",
    "HOPP": "Hopper",
    "HORN": "Horn",
    "HT": "HTML",
    "IND": "Industry",
    "INDS": "Industry",
    "INT": "Interior",
    "INTR": "Interior",
    "IT": "Interlocking Tower",
    "JP": "Japan",
    "KR": "Korea",
    "LIQ": "Liquid",
    "LND": "Land",
    "LOC": "Locomotive",
    "LOCO": "Locomotive",
    "MAIL": "Mail",
    "MESH": "Mesh",
    "MNT": "Maintenance",
    "MOBJ": "Mesh Object",
    "NACT": "Inactive",
    "NEV": "General",
    "NL": "Netherlands",
    "NZ": "New Zealand",
    "OTHR": "Other",
    "PANT": "Pantograph",
    "PASS": "Passenger",
    "PAX": "Passenger",
    "PL": "Poland",
    "PP": "People",
    "PRDC": "Product Category",
    "PROD": "Product",
    "PWAY": "Permanent Way",
    "PWL": "Power Line",
    "RACK": "Rack",
    "RCR": "Railcar",
    "RD": "Road",
    "REEF": "Refrigerator",
    "REGN": "Region",
    "RES": "Residential",
    "RLS": "Rails",
    "ROAD": "Road",
    "ROLL": "Rolling Stock",
    "RRD": "Railroad",
    "RT": "Route",
    "RU": "Rule",
    "SCEN": "Scenery",
    "SCRP": "Script",
    "SD": "Sound",
    "SEA": "Sea",
    "SEAT": "Coach",
    "SIG": "Signal",
    "SIGN": "Signal",
    "SIN": "Sign",
    "SKYS": "Sky",
    "SLIB": "Script Library",
    "SND": "Sound",
    "SNDS": "Sound Set",
    "SPC": "Special",
    "SPLN": "Spline",
    "SQ": "Script",
    "SS": "Session",
    "STA": "Station",
    "STEA": "Steam",
    "STEAM": "Steam",
    "STEM": "Steam",
    "SVLT": "Servlet",
    "SWT": "Scenery with Track",
    "SY": "Scenery",
    "TANK": "Tank",
    "TCB": "Track Circuit",
    "TDR": "Tender",
    "TEND": "Tender",
    "TEX": "Texture",
    "TH": "Thailand",
    "TK": "Track",
    "TNIC": "Controller",
    "TNIP": "Plugin",
    "TNIR": "Resource",
    "TO": "Trackside",
    "TR": "Train",
    "TRACK": "Track",
    "TRCK": "Track",
    "TSND": "Track Sound",
    "TUN": "Tunnel",
    "TUNL": "Tunnel",
    "TUNNEL": "Tunnel",
    "TURF": "Turf",
    "TURN": "Turntable",
    "TUT": "Tutorial",
    "TV": "Train Vehicle",
    "TX": "Texture",
    "TXGRP": "Texture Group",
    "UK": "United Kingdom",
    "US": "United States",
    "UTL": "Utility",
    "VE": "Vehicle",
    "VEH": "Vehicle",
    "VEHC": "Vehicle",
    "WAYP": "Waypoint",
    "WW": "Worldwide",
}


def _category_name(token: str) -> str:
    key = token.upper()
    name = _CATEGORY_NAMES.get(key)
    if name:
        return name
    if key.startswith("#"):
        return _CATEGORY_NAMES.get(key[1:], token[1:])
    return token


def category_label(code: str) -> str:
    """`TR;CMP;ESPC` → `Engine Spec`. `BD;RRD;SY;SCEN` → `Building · Railroad`."""
    parts = [part.strip() for part in code.split(";") if part.strip()]
    if not parts:
        return ""
    specific = [part for part in parts if part.upper() not in _CATEGORY_GENERIC]
    names: list[str] = []
    seen: set[str] = set()
    for part in specific or parts:
        name = _category_name(part)
        folded = name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        names.append(name)
    return " · ".join(names)


def _meta_cache_path() -> Path:
    folder = Path.home() / ".cache" / "trainz_studio"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "tu-archive-meta.json"


def _load_meta_cache() -> dict[str, list]:
    path = _meta_cache_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def scan_archive_meta(
    roots: list[Path] | None = None,
    on_batch=None,
    cache_path: Path | None = None,
    on_status=None,
    index: ContentIndex | None = None,
) -> None:
    """Author and trainz-build from config.txt / config.chump inside each tzarc.

    Local archives win over original. A disk cache keyed by mtime skips archives
    that have not changed. `on_batch(authors, builds, names, finished)` is called
    as rows are ready. `on_status(text)` reports the step that is still running.
    Usernames come from the config file, not TrainzUtil.
    """

    def status(text: str) -> None:
        if on_status is not None:
            on_status(text)

    status("Listing archives in the content folders…")
    if index is None:
        index = index_content(roots)
    chosen_arch = index.chosen()
    editing_text = index.editing_config
    status(f"{len(chosen_arch)} archives listed. Checking the author cache…")

    def _read_one(item: tuple[str, Path, int]) -> tuple[str, str, str, str, int]:
        kuid, path, stamp = item
        try:
            from .tzarc import read_tzarc_config

            author, build, username = config_identity(read_tzarc_config(path))
        except (OSError, ValueError):
            author, build, username = "", "", ""
        return kuid, author, build, username, stamp

    cache_file = cache_path if cache_path is not None else _meta_cache_path()
    cache = _load_meta_cache() if cache_path is None else {}
    if cache_path is not None and cache_path.is_file():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            cache = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            cache = {}
    authors: dict[str, str] = {}
    builds: dict[str, str] = {}
    names: dict[str, str] = {}
    pending = 0
    dirty = False

    def flush(finished: bool) -> None:
        nonlocal pending
        if on_batch is not None and (authors or builds or names or finished):
            on_batch(dict(authors), dict(builds), dict(names), finished)
        authors.clear()
        builds.clear()
        names.clear()
        pending = 0

    def take(kuid: str, author: str, build: str, username: str = "") -> None:
        nonlocal pending
        if author:
            authors[kuid] = author
        if build:
            builds[kuid] = build
        if username:
            names[kuid] = username
        if author or build or username:
            pending += 1

    misses: list[tuple[str, Path, int]] = []
    for kuid, arch in chosen_arch.items():
        path = arch.path
        stamp = arch.mtime_ns
        cached = cache.get(kuid)
        # [author, build, mtime] is a hit. Username, when present, is index 3.
        # Requiring 4 fields reopened every archive on the old cache (17k tzarc,
        # 8 threads) and that disk storm stuttered the whole app.
        if isinstance(cached, list) and len(cached) >= 3 and cached[2] == stamp:
            username = str(cached[3] or "") if len(cached) >= 4 else ""
            take(kuid, str(cached[0] or ""), str(cached[1] or ""), username)
            continue
        misses.append((kuid, path, stamp))

    flush(False)
    total = len(misses)
    if total:
        status(f"Opening {total} archives that are new or changed.")
    else:
        status("Author cache is current. No archives need opening.")
    if misses:
        workers = _read_cores(len(misses))
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_read_one, item) for item in misses]
            for fut in as_completed(futures):
                kuid, author, build, username, stamp = fut.result()
                cache[kuid] = [author, build, stamp, username]
                dirty = True
                take(kuid, author, build, username)
                done += 1
                if done == total or done % 200 == 0:
                    if done != total:
                        flush(False)
                    status(f"Reading author names · {done} of {total} archives.")

    for kuid, path in editing_text.items():
        try:
            author, build, username = config_identity(path.read_bytes())
        except OSError:
            continue
        take(kuid, author, build, username)

    flush(True)
    if dirty:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def task_outcome(raw: str) -> tuple[bool, str]:
    """Success flag and one line from a TrainzUtil edit, commit, or validate reply."""
    if launcher_blocked(raw):
        return False, "Open the Trainz Launcher first"
    text = tidy_trainzutil(raw)
    lines = [line for line in text.splitlines() if line.strip()]
    errors = re.search(r"ok\s*\(\s*(\d+)\s+errors", text, re.IGNORECASE)
    failed = bool(errors and int(errors.group(1)) > 0)
    if errors is None and "error" in text.lower():
        failed = True
    detail = ""
    for line in lines:
        if line.lower().startswith("ok ("):
            continue
        detail = line
        break
    if not detail and lines:
        detail = lines[-1]
    if not detail:
        detail = "Failed" if failed else "Done"
    return (not failed), detail[:180]


def tidy_trainzutil(text: str) -> str:
    """Drop the `; <NULL> :` prefix TrainzUtil puts on every console line."""
    out: list[str] = []
    for line in text.splitlines():
        if "<NULL>" in line:
            line = re.split(r"<NULL>\s*:", line, maxsplit=1)[-1]
        line = line.strip()
        if line:
            out.append(line)
    return "\n".join(out)


def create_cdp(exe: Path, dest: Path, kuids: list[str]) -> str:
    """Export kuids into one CDP. The batch file keeps a long list off the shell limit."""
    if not kuids:
        raise ValueError("nothing selected")
    batch = Path(tempfile.gettempdir()) / "mstn-tu-export.txt"
    quoted = " ".join(f'"{kuid}"' for kuid in kuids)
    batch.write_text(f'"createCDP" "{dest}" {quoted}\n', encoding="utf-8")
    return run_trainzutil(exe, ["@" + str(batch)], timeout=300)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _safe_arc_name(name: str) -> bool:
    parts = Path(name).parts
    if not parts:
        return False
    if Path(name).is_absolute() or name.startswith(("/", "\\")):
        return False
    return ".." not in parts


def scan_path(path: Path) -> SourceScan:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".cdp":
        return SourceScan(path, "cdp", _scan_cdp(path))
    if suffix == ".zip":
        return SourceScan(path, "zip", _scan_zip(path, ()))
    raise ValueError(f"not a zip or cdp: {path.name}")


def scan_nested_zip(source: Path, chain: tuple[str, ...], member: str) -> list[InstallJob]:
    if not _safe_arc_name(member):
        raise ValueError("unsafe zip path")
    return _scan_zip(Path(source), chain + (member,))


def _scan_cdp(path: Path) -> list[InstallJob]:
    index = open_cdp(path)
    jobs: list[InstallJob] = []
    nested = 0
    try:
        for asset in browse_cdp(load_cdp(path)):
            for fn in asset.files:
                if not fn.is_cdp or not _safe_arc_name(fn.rel_path):
                    continue
                nested += 1
                jobs.append(
                    InstallJob(
                        id=_new_id(),
                        label=Path(fn.rel_path).name,
                        kind="cdp-inner",
                        detail=f"{asset.kuid} · {fn.rel_path}",
                        can_install=True,
                        source=path,
                        member=fn.rel_path,
                        asset_kuid=asset.kuid,
                    )
                )
    except (OSError, ValueError, KeyError):
        nested = 0
        jobs.clear()
    whole = InstallJob(
        id=_new_id(),
        label=path.name,
        kind="cdp",
        detail=f"{len(index.assets)} asset{'s' if len(index.assets) != 1 else ''}",
        can_install=True,
        source=path,
        checked=nested == 0,
    )
    info: list[InstallJob] = []
    for asset in index.assets:
        info.append(
            InstallJob(
                id=_new_id(),
                label=asset.username or asset.kuid or "asset",
                kind="info",
                detail=" · ".join(bit for bit in (asset.kuid, asset.kind) if bit),
                can_install=False,
                source=path,
            )
        )
    return [whole, *jobs, *info]


def _scan_zip(path: Path, chain: tuple[str, ...]) -> list[InstallJob]:
    buf, zf = _zip_at(path, chain)
    del buf
    jobs: list[InstallJob] = []
    folders: set[str] = set()
    try:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir() or not _safe_arc_name(name):
                continue
            low = name.lower()
            if low.endswith(".cdp"):
                jobs.append(
                    InstallJob(
                        id=_new_id(),
                        label=Path(name).name,
                        kind="zip-cdp",
                        detail=name,
                        can_install=True,
                        source=path,
                        member=name,
                        chain=chain,
                    )
                )
            elif low.endswith(".zip"):
                jobs.append(
                    InstallJob(
                        id=_new_id(),
                        label=Path(name).name,
                        kind="zip-nested",
                        detail="Open to see inside",
                        can_install=False,
                        source=path,
                        member=name,
                        chain=chain,
                    )
                )
            elif low.endswith("config.txt"):
                parent = str(Path(name).parent).replace("\\", "/")
                folder = "" if parent == "." else parent
                if folder in folders:
                    continue
                folders.add(folder)
                label = Path(folder).name if folder else path.stem
                jobs.append(
                    InstallJob(
                        id=_new_id(),
                        label=label,
                        kind="zip-folder",
                        detail=folder or "(zip root)",
                        can_install=True,
                        source=path,
                        member=folder,
                        chain=chain,
                    )
                )
    finally:
        zf.close()
    if len(jobs) == 1 and jobs[0].can_install:
        jobs[0].checked = True
    return jobs


def _zip_at(path: Path, chain: tuple[str, ...]) -> tuple[io.BytesIO | None, zipfile.ZipFile]:
    if not chain:
        return None, zipfile.ZipFile(path)
    blob = path.read_bytes()
    for member in chain:
        if not _safe_arc_name(member):
            raise ValueError("unsafe zip path")
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            blob = zf.read(member)
    buf = io.BytesIO(blob)
    return buf, zipfile.ZipFile(buf)


def stage_job(job: InstallJob, dest: Path) -> tuple[str, Path]:
    """Materialise one installable. Returns ('cdp'|'folder', path)."""
    if not job.can_install:
        raise ValueError("nothing to install")
    dest.mkdir(parents=True, exist_ok=True)
    if job.kind == "cdp":
        return "cdp", job.source
    if job.kind == "cdp-inner":
        data = read_file_bytes(load_cdp(job.source), job.asset_kuid, job.member)
        out = dest / Path(job.member).name
        out.write_bytes(data)
        return "cdp", out
    if job.kind in ("zip-cdp", "zip-folder"):
        buf, zf = _zip_at(job.source, job.chain)
        del buf
        try:
            if job.kind == "zip-cdp":
                if not _safe_arc_name(job.member):
                    raise ValueError("unsafe zip path")
                out = dest / Path(job.member).name
                out.write_bytes(zf.read(job.member))
                return "cdp", out
            folder = dest / "asset"
            _extract_prefix(zf, job.member, folder)
            return "folder", folder
        finally:
            zf.close()
    raise ValueError(f"cannot stage {job.kind}")


def _extract_prefix(zf: zipfile.ZipFile, prefix: str, dest: Path) -> None:
    pref = prefix.strip("/")
    dest.mkdir(parents=True, exist_ok=True)
    wrote = False
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir() or not _safe_arc_name(name):
            continue
        if pref:
            if name != pref and not name.startswith(pref + "/"):
                continue
            rel = name[len(pref) :].lstrip("/")
        else:
            if "/" in name.strip("/"):
                continue
            rel = name
        if not rel or not _safe_arc_name(rel):
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zf.read(info))
        wrote = True
    if not wrote:
        raise ValueError("archive entry was empty")


def install_staged(
    exe: Path,
    kind: str,
    path: Path,
    on_progress=None,
    *,
    asset_count: int = 0,
) -> str:
    cmd = "installCDP" if kind == "cdp" else "installfrompath"
    args = [cmd, str(path)]
    if on_progress is None:
        return run_trainzutil(exe, args, timeout=900)
    return _install_stream(exe, args, timeout=900, on_progress=on_progress, asset_count=asset_count)


def read_install_pulse(line: str, seen: int, total: int) -> tuple[int | None, str, int]:
    """Map one TrainzUtil line to a percent, a short status, and how many assets were seen.

    Percent stays unset when the line is only chatter. A counted install line fills
    the gap from the asset total, and never claims 100 before the process exits.
    """
    text = " ".join(line.split())
    if not text:
        return None, "", seen
    low = text.lower()
    match = re.search(r"(?<!\d)(\d{1,3})\s*%", text)
    bumped = seen
    if "<kuid" in low or any(word in low for word in ("install", "commit", "import", "saving")):
        bumped = seen + 1
    pct = int(match.group(1)) if match else None
    if pct is not None:
        pct = max(0, min(99, pct))
    elif bumped != seen:
        if total > 0:
            pct = min(95, 8 + int(bumped / total * 87))
        else:
            pct = min(90, 8 + bumped * 5)
    return pct, text[:96], bumped


def _install_stream(exe: Path, args: list[str], timeout: float, on_progress, asset_count: int) -> str:
    proc = subprocess.Popen(
        [str(exe), *args],
        cwd=str(exe.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_CREATE_NO_WINDOW,
    )
    lines: list[str] = []
    pending: queue.Queue[str | None] = queue.Queue()

    def _read() -> None:
        if proc.stdout is None:
            pending.put(None)
            return
        for line in proc.stdout:
            pending.put(line)
        pending.put(None)

    threading.Thread(target=_read, daemon=True, name="trainzutil-stream").start()
    seen = 0
    on_progress(6, "Starting")
    started = time.monotonic()
    while True:
        remain = timeout - (time.monotonic() - started)
        if remain <= 0:
            proc.kill()
            raise subprocess.TimeoutExpired(args, timeout)
        try:
            line = pending.get(timeout=min(0.4, remain))
        except queue.Empty:
            if proc.poll() is not None:
                break
            continue
        if line is None:
            break
        text = line.strip()
        if not text:
            continue
        lines.append(text)
        pct, status, seen = read_install_pulse(text, seen, asset_count)
        if pct is not None and status:
            on_progress(pct, status)
    proc.wait(timeout=5)
    return "\n".join(lines).strip()


def source_row(path: Path, kind: str, source_id: str) -> dict[str, object]:
    size = format_bytes(path.stat().st_size) if path.is_file() else ""
    return {
        "sourceId": source_id,
        "name": path.name,
        "kind": kind,
        "size": size,
        "status": "Ready",
        "path": str(path),
        "percent": 0,
        "checked": True,
    }
