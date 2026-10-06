"""Trainz *.texture.txt checker — public wiki format (clean-room)."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

KNOWN_KEYS = {
    "Primary",
    "Alpha",
    "Compression",
    "NormalMapHint",
    "ModifyMap",
    "AlphaHint",
    "Tile",
    "UsageHint",
    "MipAlgorithm",
    "nonpoweroftwo",
}

VALID = {
    "Compression": {"none", "dxt1", "dxt3", "dxt5"},
    "NormalMapHint": {"none", "normalmap"},
    "ModifyMap": {"none", "flipgreen"},
    "AlphaHint": {"opaque", "semitransparent", "masked"},
    "Tile": {"s", "t", "st", "none"},
    "UsageHint": {"albedo", "normal", "parameter"},
    "MipAlgorithm": {"weight-by-alpha", "no-weight-by-alpha", "heavy-alpha"},
}

IMAGE_EXTS = {".tga", ".jpg", ".jpeg", ".bmp", ".png", ".hdr", ".dds"}

# Strip order matters: .texture.txt before .texture / .txt
_STEM_SUFFIXES = (
    ".texture.txt",
    ".texture",
    ".png",
    ".tga",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".dds",
    ".hdr",
    ".txt",
)


def texture_stem(name: str | Path) -> str:
    """Basename without .texture / image / .txt suffixes (case-insensitive).

    Examples: ``body_albedo.texture.txt`` → ``body_albedo``;
    ``foo.tga`` → ``foo``; ``bar.texture`` → ``bar``.
    """
    s = Path(name).name
    lower = s.lower()
    for _ in range(4):
        matched = False
        for suf in _STEM_SUFFIXES:
            if lower.endswith(suf):
                s = s[: -len(suf)]
                lower = s.lower()
                matched = True
                break
        if not matched:
            break
    return lower


# Map-role suffixes stripped to form a material family group key.
_MAP_ROLE_SUFFIXES = (
    ("_albedo", "albedo"),
    ("_normal", "normal"),
    ("_parameter", "parameter"),
    ("_param", "parameter"),
    ("-albedo", "albedo"),
    ("-normal", "normal"),
    ("-parameter", "parameter"),
    (".albedo", "albedo"),
    (".normal", "normal"),
    (".parameter", "parameter"),
)


def material_family(stem: str | Path) -> tuple[str, str | None]:
    """Return ``(family_key, map_role)`` for a texture stem.

    ``body_side_albedo`` → ``(\"body_side\", \"albedo\")``;
    ``window`` → ``(\"window\", None)``.
    """
    s = texture_stem(stem)
    for suf, role in _MAP_ROLE_SUFFIXES:
        if s.endswith(suf):
            return s[: -len(suf)] or s, role
    return s, None


def stems_match(have: set[str], want: set[str]) -> bool:
    """True if any stem hits exactly, or shares a material family key.

    Mat list often shows ``body_albedo`` while the mesh refs ``body`` /
    ``body.texture`` — exact set intersection misses; family match does not.
    """
    if not have or not want:
        return False
    if have & want:
        return True
    have_fam = {material_family(s)[0] for s in have if s}
    want_fam = {material_family(s)[0] for s in want if s}
    return bool(have_fam & want_fam)


@dataclass
class TexIssue:
    level: str  # error | warn | info
    message: str


@dataclass
class TextureReport:
    path: Path
    keys: dict[str, str] = field(default_factory=dict)
    issues: list[TexIssue] = field(default_factory=list)
    primary_size: tuple[int, int] | None = None
    alpha_size: tuple[int, int] | None = None

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    @property
    def summary(self) -> str:
        n_err = sum(1 for i in self.issues if i.level == "error")
        n_warn = sum(1 for i in self.issues if i.level == "warn")
        if n_err:
            return f"FAIL {n_err}e/{n_warn}w"
        if n_warn:
            return f"OK* {n_warn}w"
        return "OK"


def parse_texture_txt(text: str) -> dict[str, str]:
    """Parse key=value lines (values stripped)."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def image_size(path: Path) -> tuple[int, int] | None:
    """Read width/height without Pillow (PNG/BMP/TGA/JPEG SOF)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 24:
        return None
    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    # BMP
    if data[:2] == b"BM" and len(data) >= 26:
        w, h = struct.unpack("<ii", data[18:26])
        return int(abs(w)), int(abs(h))
    # TGA (footer or header) — uncompressed/header-only size at bytes 12-15
    if path.suffix.lower() == ".tga" and len(data) >= 18:
        w, h = struct.unpack("<HH", data[12:16])
        if w and h:
            return int(w), int(h)
    # JPEG — scan for SOF0/2
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return int(w), int(h)
            if marker == 0xD9:
                break
            if marker in (0xD8, 0x01) or (0xD0 <= marker <= 0xD7):
                i += 2
                continue
            seglen = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + seglen
    return None


@dataclass
class ImageProbe:
    """Finder-style image facts for Assets Texture table."""

    path: Path
    width: int = 0
    height: int = 0
    mode: str = ""
    channels: int = 0
    file_bytes: int = 0
    error: str = ""

    @property
    def dims(self) -> str:
        if self.width > 0 and self.height > 0:
            return f"{self.width}×{self.height}"
        return "—"

    @property
    def channel_label(self) -> str:
        if self.mode and self.channels:
            return f"{self.mode} · {self.channels}ch"
        if self.mode:
            return self.mode
        if self.channels:
            return f"{self.channels}ch"
        return "—"


def probe_image(path: Path) -> ImageProbe:
    """Width/height/mode/channels + on-disk bytes (Pillow when available)."""
    path = Path(path)
    out = ImageProbe(path=path)
    try:
        out.file_bytes = int(path.stat().st_size)
    except OSError as exc:
        out.error = str(exc)
        return out
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as img:
            out.width, out.height = int(img.size[0]), int(img.size[1])
            out.mode = str(img.mode or "")
            bands = img.getbands()
            out.channels = len(bands) if bands else 0
        return out
    except Exception as exc:  # noqa: BLE001
        sz = image_size(path)
        if sz:
            out.width, out.height = sz
            out.error = ""
            return out
        out.error = str(exc)
        return out


_ROLE_RANK = {"albedo": 0, "normal": 1, "parameter": 2}
_PBR_ROLES = frozenset(_ROLE_RANK)


def pbr_set_label(roles: set[str | None]) -> str:
    """Human set status — complete PBR trio vs missing maps."""
    present = {r for r in roles if r in _PBR_ROLES}
    if not present:
        return "plain"
    missing = sorted(_PBR_ROLES - present, key=lambda r: _ROLE_RANK[r])
    if not missing:
        return "PBR ✓"
    return "need " + "+".join(missing)


def sort_texture_paths(paths: list[Path]) -> list[tuple[Path, str, str | None, str]]:
    """Sort images into PBR sets: family → albedo/normal/parameter.

    Returns ``(path, family, role, set_label)`` rows ready for the Texture table.
    """
    enriched: list[tuple[Path, str, str | None]] = []
    for p in paths:
        fam, role = material_family(p.stem)
        enriched.append((p, fam, role))
    by_fam: dict[str, set[str | None]] = {}
    for _p, fam, role in enriched:
        by_fam.setdefault(fam, set()).add(role)
    labels = {fam: pbr_set_label(roles) for fam, roles in by_fam.items()}

    def _key(row: tuple[Path, str, str | None]) -> tuple:
        _p, fam, role = row
        return (fam.lower(), _ROLE_RANK.get(role or "", 9), _p.name.lower())

    return [(p, fam, role, labels[fam]) for p, fam, role in sorted(enriched, key=_key)]


def _resolve_image(folder: Path, name: str) -> Path | None:
    if not name:
        return None
    p = folder / name
    if p.is_file():
        return p
    # case-insensitive fallback
    lower = name.lower()
    for child in folder.iterdir():
        if child.is_file() and child.name.lower() == lower:
            return child
    return None


def check_texture_txt(path: Path) -> TextureReport:
    path = path.resolve()
    report = TextureReport(path=path)
    if not path.is_file():
        report.issues.append(TexIssue("error", "file not found"))
        return report

    # Compiled .texture (no .txt): not editable source
    if path.suffix.lower() == ".texture" and not path.name.lower().endswith(".texture.txt"):
        sib = Path(str(path) + ".txt")
        report.issues.append(
            TexIssue(
                "info",
                "Compiled/runtime .texture resource — editable form is *.texture.txt",
            )
        )
        if sib.is_file():
            return check_texture_txt(sib)
        report.issues.append(TexIssue("warn", f"no sibling {sib.name}"))
        return report

    raw = path.read_text(encoding="utf-8", errors="replace")
    # whitespace around = ?
    for i, line in enumerate(raw.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//") or "=" not in s:
            continue
        if re.search(r"\s=\s|=\s|\s=", s) and s.replace(" ", "") != s:
            # "Primary=x" is fine; "Primary = x" violates wiki strict form
            if " =" in s or "= " in s:
                report.issues.append(
                    TexIssue("warn", f"line {i}: whitespace around '=' (wiki wants none)")
                )

    keys = parse_texture_txt(raw)
    report.keys = keys

    for k in keys:
        if k not in KNOWN_KEYS:
            report.issues.append(TexIssue("warn", f"unknown key '{k}'"))

    for k, allowed in VALID.items():
        if k in keys and keys[k] and keys[k] not in allowed:
            report.issues.append(
                TexIssue("error", f"{k}={keys[k]!r} not in {sorted(allowed)}")
            )

    primary = keys.get("Primary", "")
    alpha = keys.get("Alpha", "")
    folder = path.parent

    if not primary:
        report.issues.append(TexIssue("error", "missing Primary="))
    else:
        if Path(primary).suffix.lower() not in IMAGE_EXTS:
            report.issues.append(TexIssue("warn", f"Primary ext unusual: {primary}"))
        prim_path = _resolve_image(folder, primary)
        if prim_path is None:
            report.issues.append(TexIssue("error", f"Primary image missing: {primary}"))
        else:
            sz = image_size(prim_path)
            report.primary_size = sz
            if sz is None:
                report.issues.append(TexIssue("warn", f"could not read size: {primary}"))
            else:
                w, h = sz
                npot = keys.get("nonpoweroftwo") == "1"
                if not npot and (not _is_power_of_two(w) or not _is_power_of_two(h)):
                    report.issues.append(
                        TexIssue("error", f"Primary size {w}x{h} not power-of-two")
                    )
                if w > 4096 or h > 4096:
                    report.issues.append(TexIssue("error", f"Primary {w}x{h} exceeds 4096"))

    if alpha:
        if Path(alpha).suffix.lower() not in IMAGE_EXTS:
            report.issues.append(TexIssue("warn", f"Alpha ext unusual: {alpha}"))
        alpha_path = _resolve_image(folder, alpha)
        if alpha_path is None:
            report.issues.append(TexIssue("error", f"Alpha image missing: {alpha}"))
        else:
            sz = image_size(alpha_path)
            report.alpha_size = sz
            if report.primary_size and sz and sz != report.primary_size:
                report.issues.append(
                    TexIssue(
                        "error",
                        f"Alpha size {sz[0]}x{sz[1]} != Primary "
                        f"{report.primary_size[0]}x{report.primary_size[1]}",
                    )
                )
            if primary and alpha == primary:
                report.issues.append(
                    TexIssue("info", "Primary=Alpha same file (RGBA source expected)")
                )

    # Hint consistency
    nm = keys.get("NormalMapHint", "")
    usage = keys.get("UsageHint", "")
    name_l = path.name.lower()
    if "normal" in name_l and nm != "normalmap":
        report.issues.append(
            TexIssue("warn", "filename suggests normal map but NormalMapHint≠normalmap")
        )
    if usage == "normal" and nm != "normalmap":
        report.issues.append(TexIssue("warn", "UsageHint=normal without NormalMapHint=normalmap"))
    if "parameter" in name_l and usage and usage != "parameter":
        report.issues.append(TexIssue("warn", f"parameter-like name but UsageHint={usage}"))
    if "albedo" in name_l and usage and usage != "albedo":
        report.issues.append(TexIssue("warn", f"albedo-like name but UsageHint={usage}"))

    return report


def scan_folder(folder: Path) -> list[TextureReport]:
    folder = Path(folder)
    paths = sorted(folder.glob("*.texture.txt"))
    # also bare .texture without .txt twin noted
    for p in sorted(folder.glob("*.texture")):
        if p.name.lower().endswith(".texture.txt"):
            continue
        if not Path(str(p) + ".txt").is_file():
            paths.append(p)
    return [check_texture_txt(p) for p in paths]


def resolve_primary_image(report: TextureReport) -> Path | None:
    """Return the Primary= image next to a .texture.txt (for 3D preview)."""
    primary = report.keys.get("Primary", "")
    if not primary:
        return None
    return _resolve_image(report.path.parent, primary)


def format_report(r: TextureReport) -> str:
    lines = [f"{r.path.name}  [{r.summary}]"]
    if r.keys:
        kv = " ".join(f"{k}={v!r}" for k, v in r.keys.items())
        lines.append(f"  {kv}")
    if r.primary_size:
        lines.append(f"  Primary size: {r.primary_size[0]}x{r.primary_size[1]}")
    for iss in r.issues:
        lines.append(f"  {iss.level}: {iss.message}")
    return "\n".join(lines)


# Preferred authoring order (wiki / TrainzFileEditor-style generators).
_TEXTURE_KEY_ORDER = (
    "Primary",
    "Alpha",
    "Compression",
    "NormalMapHint",
    "ModifyMap",
    "AlphaHint",
    "Tile",
    "UsageHint",
    "MipAlgorithm",
    "nonpoweroftwo",
)


def format_texture_txt(keys: dict[str, str], *, skip_empty: bool = True) -> str:
    """Serialize key=value lines (no spaces around '=')."""
    lines: list[str] = []
    seen: set[str] = set()
    for key in _TEXTURE_KEY_ORDER:
        if key not in keys:
            continue
        val = keys[key]
        if skip_empty and (val is None or str(val).strip() == ""):
            continue
        lines.append(f"{key}={val}")
        seen.add(key)
    for key, val in keys.items():
        if key in seen:
            continue
        if skip_empty and (val is None or str(val).strip() == ""):
            continue
        lines.append(f"{key}={val}")
    return "\n".join(lines) + ("\n" if lines else "")


def write_texture_txt(path: Path, keys: dict[str, str], *, skip_empty: bool = True) -> Path:
    path = Path(path)
    name = path.name
    if name.lower().endswith(".texture"):
        path = Path(str(path) + ".txt")
    elif not name.lower().endswith(".texture.txt"):
        if path.suffix.lower() == ".txt":
            path = path.with_name(path.stem + ".texture.txt")
        else:
            path = path.with_name(path.name + ".texture.txt")
    path.write_text(format_texture_txt(keys, skip_empty=skip_empty), encoding="utf-8", newline="\n")
    return path


def default_texture_keys(
    *,
    primary: str,
    alpha: str = "",
    usage: str | None = None,
    normal: bool = False,
    tile: str = "st",
    compression: str = "",
) -> dict[str, str]:
    keys: dict[str, str] = {"Primary": primary}
    if alpha:
        keys["Alpha"] = alpha
    if compression:
        keys["Compression"] = compression
    if normal:
        keys["NormalMapHint"] = "normalmap"
    if tile:
        keys["Tile"] = tile
    if usage:
        keys["UsageHint"] = usage
    elif normal:
        keys["UsageHint"] = "normal"
    return keys


def keys_for_image(
    primary: str,
    *,
    alpha: str = "",
    tile: str = "st",
    compression: str = "",
) -> dict[str, str]:
    """PBR-aware defaults from filename (albedo / normal / parameter), like TXT Generator."""
    _, role = material_family(primary)
    return default_texture_keys(
        primary=primary,
        alpha=alpha,
        usage=role,
        normal=role == "normal",
        tile=tile,
        compression=compression,
    )
