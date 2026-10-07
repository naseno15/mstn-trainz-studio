"""Trainz mesh/texture/config VE rules — local scan + safe auto-fixes.

File-local checks only (no Content Manager DB / GameScript compile).
Maps findings to stable VE numbers from TrainzOnline Validation Errors.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .image_prep import calculate_target_size, process_image
from .lm import parse_lm_txt, read_lm_txt
from .mat_names import apply_renames, scan_materials, suggested_mapping
from .texture import (
    IMAGE_EXTS,
    check_texture_txt,
    image_size,
    keys_for_image,
    parse_texture_txt,
    probe_image,
    write_texture_txt,
)
from .ve39 import fix_ve39, is_uniform_color, scan_ve39

# ── constants ───────────────────────────────────────────────

_HIGH_POLY_FACE_WARN = 5000  # VE81 soft threshold when no sibling .lm.txt
_MAX_TEX_DIM = 4096
_TRAINCAR_REQUIRED_ATTS = ("a.bog0", "a.bog1")
_OBSOLETE_TOP_TAGS = frozenset(
    {
        "light",  # old traincar light → VE44
        "nightmode",
        "cabinsway",
    }
)
_CUBEMAP_NAME_RE = re.compile(r"(cube|cubemap|skybox)", re.I)
_ANSI_NAME_RE = re.compile(r"^[\x20-\x7E]+$")
_KIND_RE = re.compile(r'(?im)^\s*kind\s+"([^"]+)"')
_KIND_BARE_RE = re.compile(r"(?im)^\s*kind\s+(\S+)")
_BUILD_RE = re.compile(r"(?im)^\s*trainz-build\s+([0-9.]+)")
_ATT_TAG_RE = re.compile(
    r'(?im)^\s*(?:att|attachment)\s+"([^"]+)"',
)
_MESH_FILE_RE = re.compile(
    r'(?im)^\s*mesh\s+"([^"]+\.(?:im|trainzmesh|fbx|lm))"',
)


@dataclass(frozen=True)
class VeFinding:
    code: int  # VE number; 0 = studio-only (material names)
    level: str  # error | warn | info
    path: Path
    message: str
    fixable: bool = False
    fix_kind: str = ""  # ve39 | pot | texture_txt | mat_name | alpha_size


@dataclass
class VeReport:
    path: Path
    findings: list[VeFinding] = field(default_factory=list)

    @property
    def codes(self) -> list[int]:
        return sorted({f.code for f in self.findings if f.code > 0})

    @property
    def status(self) -> str:
        """Compact Status-column text."""
        if not self.findings:
            return "OK"
        errs = [f for f in self.findings if f.level == "error"]
        pool = errs or self.findings
        codes = []
        seen: set[int] = set()
        for f in pool:
            if f.code <= 0 or f.code in seen:
                continue
            seen.add(f.code)
            codes.append(f.code)
            if len(codes) >= 3:
                break
        extra = len({f.code for f in pool if f.code > 0}) - len(codes)
        if not codes:
            return pool[0].message[:28]
        text = "·".join(f"VE{c}" for c in codes)
        if extra > 0:
            text += f"+{extra}"
        # VE39 gets colour swatch when alone
        if codes == [39]:
            for f in self.findings:
                if f.code == 39 and "#" in f.message:
                    hex_bit = f.message.rsplit("#", 1)[-1].strip()
                    if len(hex_bit) >= 6:
                        return f"VE39 #{hex_bit[:6]}"
        return text

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.level == "warn")


def format_findings(findings: list[VeFinding]) -> str:
    if not findings:
        return "(no VE issues)"
    lines: list[str] = []
    for f in findings:
        tag = f"VE{f.code}" if f.code else "MAT"
        fix = " [fixable]" if f.fixable else ""
        lines.append(f"{tag} {f.level}: {f.path.name} — {f.message}{fix}")
    return "\n".join(lines)


def format_report(report: VeReport) -> str:
    head = f"{report.path.name}  [{report.status}]"
    body = format_findings(report.findings)
    return f"{head}\n{body}" if report.findings else f"{head}\n  OK"


# ── image / texture ─────────────────────────────────────────


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def scan_image(path: Path) -> VeReport:
    """VE36–40, 66, 167 (+ VE39) for one image file."""
    path = Path(path)
    report = VeReport(path=path)
    if not path.is_file():
        report.findings.append(
            VeFinding(30, "error", path, "file does not exist", False)
        )
        return report

    name = path.name
    if not _ANSI_NAME_RE.match(name):
        report.findings.append(
            VeFinding(66, "error", path, "filename contains non-ANSI characters", False)
        )

    probe = probe_image(path)
    if probe.error and not (probe.width and probe.height):
        report.findings.append(
            VeFinding(36, "error", path, f"texture failed to load: {probe.error}", False)
        )
        return report

    w, h = probe.width, probe.height
    if w <= 0 or h <= 0:
        sz = image_size(path)
        if sz:
            w, h = sz
    if w <= 0 or h <= 0:
        report.findings.append(
            VeFinding(36, "error", path, "could not read image size", False)
        )
        return report

    if not _is_power_of_two(w) or not _is_power_of_two(h):
        tw, th = calculate_target_size(w, h, "pot", pot_down=True)
        report.findings.append(
            VeFinding(
                37,
                "error",
                path,
                f"size {w}x{h} is not power-of-2 (→ {tw}x{th})",
                True,
                "pot",
            )
        )

    if _CUBEMAP_NAME_RE.search(path.stem) and w != h:
        report.findings.append(
            VeFinding(
                38,
                "error",
                path,
                f"cubemap texture is not square ({w}x{h})",
                False,
            )
        )

    if w > _MAX_TEX_DIM or h > _MAX_TEX_DIM:
        report.findings.append(
            VeFinding(
                167,
                "error",
                path,
                f"source image too large ({w}x{h} > {_MAX_TEX_DIM})",
                True,
                "pot",
            )
        )

    try:
        with Image.open(path) as img:
            uniform, color = is_uniform_color(img)
            if uniform:
                hex_c = "#{:02X}{:02X}{:02X}".format(color[0], color[1], color[2])
                report.findings.append(
                    VeFinding(
                        39,
                        "error",
                        path,
                        f"uniform / solid color {hex_c}",
                        True,
                        "ve39",
                    )
                )
    except Exception as exc:  # noqa: BLE001
        report.findings.append(
            VeFinding(36, "error", path, f"texture failed to load: {exc}", False)
        )

    return report


def scan_texture_txt(path: Path) -> VeReport:
    """Map check_texture_txt issues → VE65/67/68/113–116/37."""
    path = Path(path)
    report = VeReport(path=path)
    tr = check_texture_txt(path)
    for iss in tr.issues:
        msg = iss.message
        low = msg.lower()
        code = 0
        fixable = False
        fix_kind = ""
        if "missing primary" in low:
            code, fixable, fix_kind = 67, True, "texture_txt"
        elif "primary image missing" in low or "alpha image missing" in low:
            code = 115 if "texture" in low else 30
        elif "not power-of-two" in low:
            code, fixable, fix_kind = 37, True, "pot"
        elif "alpha size" in low and "!=" in low:
            code, fixable, fix_kind = 68, True, "alpha_size"
        elif "exceeds 4096" in low:
            code = 167
        elif "image file" in low and "texture.txt" in low:
            code = 113
        elif "no sibling" in low or "compiled/runtime" in low:
            code = 245
        elif "file not found" in low:
            code = 101
        elif iss.level == "error":
            code = 65
        elif iss.level == "warn":
            code = 65
        if code:
            report.findings.append(
                VeFinding(
                    code,
                    iss.level if iss.level in ("error", "warn", "info") else "warn",
                    path,
                    msg,
                    fixable,
                    fix_kind,
                )
            )
        else:
            report.findings.append(
                VeFinding(0, iss.level, path, msg, False)
            )
    return report


def scan_texture_folder(folder: Path) -> list[VeReport]:
    """Images + texture.txt + orphan images missing *.texture.txt (VE65)."""
    folder = Path(folder)
    reports: list[VeReport] = []
    if not folder.is_dir():
        return reports

    images = sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    texts = sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and (
            p.name.lower().endswith(".texture.txt")
            or (p.suffix.lower() == ".texture" and not p.name.lower().endswith(".texture.txt"))
        )
    )

    covered_stems: set[str] = set()
    for t in texts:
        r = scan_texture_txt(t)
        reports.append(r)
        try:
            keys = parse_texture_txt(t.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            keys = {}
        primary = keys.get("Primary", "")
        if primary:
            covered_stems.add(Path(primary).stem.lower())
        covered_stems.add(t.name.lower().removesuffix(".texture.txt").removesuffix(".texture"))

    for img in images:
        r = scan_image(img)
        stem = img.stem.lower()
        txt = folder / f"{img.stem}.texture.txt"
        if not txt.is_file() and stem not in covered_stems:
            r.findings.append(
                VeFinding(
                    65,
                    "error",
                    img,
                    f"missing {img.stem}.texture.txt",
                    True,
                    "texture_txt",
                )
            )
        reports.append(r)

    return reports


# ── mesh / LM / materials ───────────────────────────────────


def _attachment_names(path: Path) -> tuple[list[str], str]:
    """Return (names, error). Fast path — no Assimp FBX geo."""
    path = Path(path)
    suf = path.suffix.lower()
    try:
        if suf == ".trainzmesh":
            from .loaders import parse_trainzmesh_attachments

            atts = parse_trainzmesh_attachments(path.read_bytes())
            return [a.name for a in atts], ""
        if suf == ".im":
            from ..lib.im_editor.core import parse_attachments

            atts = parse_attachments(path.read_bytes())
            return [a.name for a in atts], ""
        if suf == ".fbx":
            # ponytail: FBX att empty names need Assimp — skip heavy load in batch
            return [], ""
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)
    return [], ""


def _face_count_trainzmesh(path: Path) -> int | None:
    try:
        from .loaders import load_trainzmesh

        sc = load_trainzmesh(path, preview_fast=True)
        return int(sc.face_count)
    except Exception:  # noqa: BLE001
        return None


def scan_mesh(path: Path) -> VeReport:
    """Material names, attachments, load, high-poly / LOD hints."""
    path = Path(path)
    report = VeReport(path=path)
    if not path.is_file():
        report.findings.append(
            VeFinding(72, "error", path, "unable to load mesh — file missing", False)
        )
        return report

    suf = path.suffix.lower()
    if suf == ".pm":
        report.findings.append(
            VeFinding(
                86,
                "error",
                path,
                "legacy .pm no longer supported — switch to .lm",
                False,
            )
        )

    # Material names (studio rule → surfaced as MAT / linked to VE173)
    try:
        issues = scan_materials(path)
        bad = [i for i in issues if i.needs_fix]
        for iss in bad:
            report.findings.append(
                VeFinding(
                    173,
                    "error",
                    path,
                    f"material '{iss.name}': {iss.detail}",
                    bool(iss.suggested),
                    "mat_name",
                )
            )
    except Exception as exc:  # noqa: BLE001
        report.findings.append(
            VeFinding(72, "warn", path, f"material scan failed: {exc}", False)
        )

    names, err = _attachment_names(path)
    if err:
        report.findings.append(
            VeFinding(72, "error", path, f"unable to read attachments: {err}", False)
        )
    for n in names:
        if not n or not n.strip():
            report.findings.append(
                VeFinding(285, "error", path, "empty attachment name in mesh", False)
            )
        elif n.startswith("a.") is False and n.startswith("a") is False:
            # Trainz attachments are usually a.*
            pass

    # High-poly without LOD table beside the mesh
    if suf == ".trainzmesh":
        faces = _face_count_trainzmesh(path)
        if faces is not None and faces >= _HIGH_POLY_FACE_WARN:
            sibling_lm = path.with_suffix(".lm.txt")
            alt_lm = path.parent / f"{path.stem}.lm.txt"
            if not sibling_lm.is_file() and not alt_lm.is_file():
                report.findings.append(
                    VeFinding(
                        81,
                        "warn",
                        path,
                        f"high-poly mesh ({faces} faces) should have LOD (.lm.txt)",
                        False,
                    )
                )

    # FBX version probe
    if suf == ".fbx":
        try:
            data = path.read_bytes()[:64]
            if data.startswith(b"Kaydara FBX Binary"):
                if len(data) >= 27:
                    ver = int.from_bytes(data[23:27], "little")
                    if ver and ver < 7100:
                        report.findings.append(
                            VeFinding(
                                183,
                                "warn",
                                path,
                                f"FBX binary version {ver} may be unsupported older format",
                                False,
                            )
                        )
        except OSError as exc:
            report.findings.append(
                VeFinding(72, "error", path, f"unable to load mesh: {exc}", False)
            )

    return report


def scan_lm_txt(path: Path) -> VeReport:
    path = Path(path)
    report = VeReport(path=path)
    if not path.is_file():
        report.findings.append(
            VeFinding(158, "error", path, "unable to open .lm.txt", False)
        )
        return report
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        lm = parse_lm_txt(text)
    except Exception as exc:  # noqa: BLE001
        report.findings.append(
            VeFinding(159, "error", path, f"unable to parse .lm.txt: {exc}", False)
        )
        return report

    if not lm.meshes:
        report.findings.append(
            VeFinding(160, "error", path, "no mesh keys found in .lm.txt", False)
        )
        return report

    n = len(lm.meshes)
    if n < 2:
        report.findings.append(
            VeFinding(
                84,
                "warn",
                path,
                "LM has only a single mesh — may hurt performance",
                False,
            )
        )
    report.findings.append(
        VeFinding(161, "info", path, f"{n} LOD(s) in .lm.txt", False)
    )

    # widths must be ascending unique
    widths = [m.width for m in lm.sorted_meshes()]
    if widths != sorted(set(widths)):
        report.findings.append(
            VeFinding(
                215,
                "error",
                path,
                f"invalid LOD widths (need unique ascending): {widths}",
                False,
            )
        )

    folder = path.parent
    att_sets: list[set[str]] = []
    for mesh in lm.sorted_meshes():
        mesh_path = folder / mesh.name
        if not mesh_path.is_file():
            # try stem swaps
            alt = folder / Path(mesh.name).name
            if not alt.is_file():
                report.findings.append(
                    VeFinding(
                        30,
                        "error",
                        path,
                        f"LOD mesh missing: {mesh.name}",
                        False,
                    )
                )
                continue
            mesh_path = alt
        names, _ = _attachment_names(mesh_path)
        att_sets.append(set(names))

    # VE162: lower LOD introduces new attachment
    if len(att_sets) >= 2:
        base = att_sets[0]
        for i, atts in enumerate(att_sets[1:], start=1):
            extra = atts - base
            for a in sorted(extra):
                report.findings.append(
                    VeFinding(
                        162,
                        "error",
                        path,
                        f"LOD[{i}] introduces new attachment: {a}",
                        False,
                    )
                )

    return report


def scan_mesh_folder(folder: Path) -> list[VeReport]:
    folder = Path(folder)
    reports: list[VeReport] = []
    if not folder.is_dir():
        return reports

    meshes = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".trainzmesh", ".im", ".fbx", ".pm"}
    ]
    lms = [
        p
        for p in folder.iterdir()
        if p.is_file() and (p.name.lower().endswith(".lm.txt") or p.suffix.lower() == ".lm")
    ]

    referenced: set[str] = set()
    for lm_path in lms:
        r = scan_lm_txt(lm_path)
        reports.append(r)
        try:
            lm = read_lm_txt(lm_path)
            for m in lm.meshes:
                referenced.add(Path(m.name).name.lower())
        except Exception:  # noqa: BLE001
            pass

    cfg = folder / "config.txt"
    cfg_meshes: set[str] = set()
    cfg_atts: set[str] = set()
    kind = ""
    if cfg.is_file():
        cr = scan_config(cfg)
        reports.append(cr)
        kind = _config_kind(cfg)
        cfg_meshes, cfg_atts = _config_mesh_and_atts(cfg)

    for mesh in sorted(meshes, key=lambda p: p.name.lower()):
        r = scan_mesh(mesh)
        name_l = mesh.name.lower()
        # VE268 unused when neither lm nor config references it
        if referenced or cfg_meshes:
            stem_alts = {name_l, mesh.stem.lower() + ".im", mesh.stem.lower() + ".trainzmesh"}
            hit = bool(stem_alts & referenced) or bool(stem_alts & {m.lower() for m in cfg_meshes})
            if not hit and name_l not in {Path(m).name.lower() for m in cfg_meshes}:
                # also match stem in config mesh paths
                if not any(mesh.stem.lower() in m.lower() for m in cfg_meshes):
                    r.findings.append(
                        VeFinding(
                            268,
                            "warn",
                            mesh,
                            "mesh file appears unused (not in .lm.txt / mesh-table)",
                            False,
                        )
                    )
        reports.append(r)

    # Attachment cross-check: config att vs mesh atts
    if cfg_atts and meshes:
        union: set[str] = set()
        for mesh in meshes:
            names, _ = _attachment_names(mesh)
            union.update(names)
        for att in sorted(cfg_atts):
            if att and att not in union:
                reports.append(
                    VeReport(
                        path=cfg,
                        findings=[
                            VeFinding(
                                15,
                                "error",
                                cfg,
                                f"attachment '{att}' not found on any mesh in folder",
                                False,
                            )
                        ],
                    )
                )

    if kind == "traincar" and meshes:
        union = set()
        for mesh in meshes:
            names, _ = _attachment_names(mesh)
            union.update(names)
        for req in _TRAINCAR_REQUIRED_ATTS:
            if req not in union:
                reports.append(
                    VeReport(
                        path=cfg if cfg.is_file() else meshes[0],
                        findings=[
                            VeFinding(
                                201,
                                "error",
                                cfg if cfg.is_file() else meshes[0],
                                f"traincar missing required attachment: {req}",
                                False,
                            )
                        ],
                    )
                )
        bogeys = [n for n in union if n.startswith("a.bog")]
        if len(bogeys) < 2:
            reports.append(
                VeReport(
                    path=cfg if cfg.is_file() else meshes[0],
                    findings=[
                        VeFinding(
                            212,
                            "error",
                            cfg if cfg.is_file() else meshes[0],
                            "traincar asset must have at least two bogeys (a.bog*)",
                            False,
                        )
                    ],
                )
            )

    return reports


# ── config ──────────────────────────────────────────────────


def _config_kind(path: Path) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = _KIND_RE.search(text) or _KIND_BARE_RE.search(text)
    return (m.group(1).strip().strip('"').lower() if m else "")


def _config_mesh_and_atts(path: Path) -> tuple[set[str], set[str]]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set(), set()
    meshes = {m.group(1) for m in _MESH_FILE_RE.finditer(text)}
    atts = {m.group(1) for m in _ATT_TAG_RE.finditer(text)}
    return meshes, atts


def _top_level_tags(text: str) -> list[str]:
    """Rough top-level tag names (indent depth 0)."""
    tags: list[str] = []
    depth = 0
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        parts = stripped.replace("{", " ").replace("}", " ").split()
        if indent == 0 and parts:
            key = parts[0].strip().strip('"').lower()
            if key and key not in ("{", "}"):
                tags.append(key)
        depth += line.count("{") - line.count("}")
        if depth < 0:
            depth = 0
    return tags


def scan_config(path: Path) -> VeReport:
    path = Path(path)
    report = VeReport(path=path)
    if not path.is_file():
        report.findings.append(
            VeFinding(101, "error", path, "config file does not exist", False)
        )
        return report
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        report.findings.append(
            VeFinding(101, "error", path, str(exc), False)
        )
        return report

    kind_m = _KIND_RE.search(text) or _KIND_BARE_RE.search(text)
    if not kind_m:
        report.findings.append(
            VeFinding(49, "error", path, "required tag 'kind' is not present", False)
        )
    build_m = _BUILD_RE.search(text)
    if build_m:
        try:
            build = float(build_m.group(1))
            if build < 3.5:
                report.findings.append(
                    VeFinding(
                        48,
                        "error",
                        path,
                        f"obsolete trainz-build {build_m.group(1)} (raise to 4.x+)",
                        False,
                    )
                )
        except ValueError:
            report.findings.append(
                VeFinding(88, "warn", path, "unrecognised trainz-build value", False)
            )
    else:
        report.findings.append(
            VeFinding(88, "warn", path, "trainz-build tag missing", False)
        )

    # duplicate top-level-ish tags (soft)
    tops = _top_level_tags(text)
    seen: dict[str, int] = {}
    for t in tops:
        seen[t] = seen.get(t, 0) + 1
    for t, n in seen.items():
        if n > 1 and t not in ("mesh", "effects", "0", "1", "2", "3", "4", "5"):
            # many repeated numeric containers are normal; flag known uniques
            if t in ("kind", "kuid", "username", "trainz-build", "mesh-table", "bogeys"):
                report.findings.append(
                    VeFinding(
                        93,
                        "error",
                        path,
                        f"duplicate '{t}' tags/containers",
                        False,
                    )
                )

    for tag in _OBSOLETE_TOP_TAGS:
        if re.search(rf"(?im)^\s*{re.escape(tag)}\b", text):
            report.findings.append(
                VeFinding(
                    44,
                    "error",
                    path,
                    f"tag '{tag}' is obsolete — remove or migrate",
                    False,
                )
            )

    # mesh files referenced but missing
    folder = path.parent
    meshes, atts = _config_mesh_and_atts(path)
    for m in sorted(meshes):
        if not (folder / Path(m).name).is_file() and not (folder / m).is_file():
            report.findings.append(
                VeFinding(
                    30,
                    "error",
                    path,
                    f"mesh-table refers to nonexistent file: {m}",
                    False,
                )
            )

    # effects without looking deep — if 'att' present without att-parent nearby is hard;
    # flag empty att strings
    for a in atts:
        if not a.strip():
            report.findings.append(
                VeFinding(18, "error", path, "empty attachment reference in config", False)
            )

    return report


# ── catalog row (Texture table) ─────────────────────────────


def catalog_image(path: Path) -> dict:
    """One Texture-table row: probe + multi-VE status."""
    path = Path(path)
    probe = probe_image(path)
    report = scan_image(path)
    # also VE65 if sibling texture.txt missing
    txt = path.with_name(path.stem + ".texture.txt")
    if path.is_file() and path.suffix.lower() in IMAGE_EXTS and not txt.is_file():
        report.findings.append(
            VeFinding(
                65,
                "error",
                path,
                f"missing {txt.name}",
                True,
                "texture_txt",
            )
        )
    status = report.status
    return {
        "path": path,
        "dims": probe.dims,
        "channels": probe.channel_label,
        "bytes": probe.file_bytes,
        "status": status,
        "uniform": any(f.code == 39 for f in report.findings),
        "error": probe.error or "",
        "codes": report.codes,
        "findings": report.findings,
        "report": report,
    }


# ── fixes ───────────────────────────────────────────────────


def fix_finding(finding: VeFinding, *, bak: bool = True) -> tuple[bool, str]:
    """Apply one safe auto-fix. Returns (ok, message)."""
    path = Path(finding.path)
    kind = finding.fix_kind
    if not finding.fixable or not kind:
        return False, "not fixable"

    if kind == "ve39":
        return fix_ve39(path, bak=bak)

    if kind == "pot":
        if not path.is_file():
            return False, "not found"
        if bak:
            bak_path = path.with_suffix(path.suffix + ".bak")
            if not bak_path.is_file():
                shutil.copy2(path, bak_path)
        # in-place PoT (and shrink if >4096 via pot then max)
        ok, dest, msg = process_image(
            path,
            resize_mode="pot",
            pot_down=True,
            out_path=path,
        )
        if ok and (finding.code == 167 or "4096" in finding.message):
            # second pass clamp
            ok2, _, msg2 = process_image(
                path,
                resize_mode="max",
                max_dim=_MAX_TEX_DIM,
                pot_down=True,
                out_path=path,
            )
            return ok2, f"PoT/max: {msg} · {msg2}"
        return ok, f"PoT: {msg}"

    if kind == "texture_txt":
        # image → write sibling texture.txt
        if path.suffix.lower() in IMAGE_EXTS:
            keys = keys_for_image(path.name)
            out = write_texture_txt(path.with_name(path.stem + ".texture.txt"), keys)
            return True, f"wrote {out.name}"
        # texture.txt with missing Primary — fill from stem
        if path.name.lower().endswith(".texture.txt"):
            keys = parse_texture_txt(path.read_text(encoding="utf-8", errors="replace"))
            if not keys.get("Primary"):
                stem = path.name[: -len(".texture.txt")]
                for ext in (".tga", ".png", ".bmp", ".jpg", ".jpeg", ".dds"):
                    cand = path.with_name(stem + ext)
                    if cand.is_file():
                        keys = keys_for_image(cand.name)
                        break
                if not keys.get("Primary"):
                    keys = keys_for_image(f"{stem}.tga")
            write_texture_txt(path, keys)
            return True, f"updated {path.name}"
        return False, "no image/texture.txt"

    if kind == "alpha_size":
        # resize Alpha image to Primary size (in-place + bak)
        if not path.name.lower().endswith(".texture.txt"):
            return False, "need .texture.txt"
        keys = parse_texture_txt(path.read_text(encoding="utf-8", errors="replace"))
        prim = keys.get("Primary", "")
        alpha = keys.get("Alpha", "")
        if not prim or not alpha:
            return False, "missing Primary/Alpha"
        folder = path.parent
        p_img = folder / prim
        a_img = folder / alpha
        if not p_img.is_file() or not a_img.is_file():
            return False, "Primary/Alpha file missing"
        psz = image_size(p_img)
        if not psz:
            return False, "cannot read Primary size"
        if bak:
            bak_path = a_img.with_suffix(a_img.suffix + ".bak")
            if not bak_path.is_file():
                shutil.copy2(a_img, bak_path)
        ok, _, msg = process_image(
            a_img,
            resize_mode="exact",
            target_w=psz[0],
            target_h=psz[1],
            out_path=a_img,
        )
        return ok, f"Alpha → {psz[0]}x{psz[1]}: {msg}"

    if kind == "mat_name":
        issues = scan_materials(path)
        mapping = suggested_mapping(issues)
        if not mapping:
            return False, "no renames"
        n = apply_renames(path, mapping, backup=bak)
        return True, f"{n} material rename(s)"

    return False, f"unknown fix {kind}"


def fix_report(report: VeReport, *, bak: bool = True) -> list[tuple[VeFinding, bool, str]]:
    """Fix all fixable findings on a report (dedupe by path+kind)."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[VeFinding, bool, str]] = []
    for f in report.findings:
        if not f.fixable:
            continue
        key = (str(f.path.resolve()) if f.path.exists() else str(f.path), f.fix_kind)
        if key in seen:
            continue
        seen.add(key)
        ok, msg = fix_finding(f, bak=bak)
        out.append((f, ok, msg))
    return out


def fix_reports(reports: list[VeReport], *, bak: bool = True) -> list[tuple[VeFinding, bool, str]]:
    results: list[tuple[VeFinding, bool, str]] = []
    for r in reports:
        results.extend(fix_report(r, bak=bak))
    return results


def scan_sound(path: Path) -> VeReport:
    """VE102 — basic WAV container check (PCM RIFF)."""
    path = Path(path)
    report = VeReport(path=path)
    if not path.is_file():
        report.findings.append(
            VeFinding(102, "error", path, "sound file does not exist", False)
        )
        return report
    suf = path.suffix.lower()
    if suf not in {".wav", ".wave"}:
        # mp3/ogg etc. — Trainz wants wav; warn only
        report.findings.append(
            VeFinding(
                102,
                "warn",
                path,
                f"not a .wav file ({suf or 'no ext'}) — Trainz soundscript expects WAV",
                False,
            )
        )
        return report
    try:
        data = path.read_bytes()[:64]
    except OSError as exc:
        report.findings.append(
            VeFinding(102, "error", path, f"failed to read sound: {exc}", False)
        )
        return report
    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        report.findings.append(
            VeFinding(102, "error", path, "not a valid RIFF/WAVE file", False)
        )
    return report


def scan_asset_folder(folder: Path) -> list[VeReport]:
    """Full local asset pass: config + mesh/LOD + textures."""
    folder = Path(folder)
    reports: list[VeReport] = []
    if not folder.is_dir():
        return reports
    cfg = folder / "config.txt"
    if cfg.is_file():
        reports.append(scan_config(cfg))
    reports.extend(scan_mesh_folder(folder))
    reports.extend(scan_texture_folder(folder))
    return reports


def summarize_reports(reports: list[VeReport]) -> dict:
    """Compact counts for status bar / dialog header."""
    hits = [r for r in reports if r.findings]
    errors = sum(r.error_count for r in reports)
    warns = sum(r.warn_count for r in reports)
    codes: list[int] = []
    seen: set[int] = set()
    for r in reports:
        for c in r.codes:
            if c not in seen:
                seen.add(c)
                codes.append(c)
    codes.sort()
    code_txt = "·".join(f"VE{c}" for c in codes[:6])
    if len(codes) > 6:
        code_txt += f"+{len(codes) - 6}"
    if errors or warns:
        line = f"{len(hits)} report(s) · {errors}e/{warns}w"
        if code_txt:
            line += f" · {code_txt}"
    else:
        line = "OK — no VE hits"
    return {
        "hits": len(hits),
        "errors": errors,
        "warns": warns,
        "codes": codes,
        "line": line,
    }


def scan_paths(paths: list[Path]) -> list[VeReport]:
    """Dispatch each path to the right scanner (app-wide entry)."""
    reports: list[VeReport] = []
    for path in paths:
        p = Path(path)
        if p.is_dir():
            reports.extend(scan_asset_folder(p))
            continue
        name = p.name.lower()
        suf = p.suffix.lower()
        if name.endswith(".texture.txt") or suf == ".texture":
            reports.append(scan_texture_txt(p))
        elif suf in IMAGE_EXTS:
            reports.append(scan_image(p))
            # VE65 sibling
            if not p.with_name(p.stem + ".texture.txt").is_file():
                reports[-1].findings.append(
                    VeFinding(
                        65,
                        "error",
                        p,
                        f"missing {p.stem}.texture.txt",
                        True,
                        "texture_txt",
                    )
                )
        elif name.endswith(".lm.txt") or suf == ".lm":
            reports.append(scan_lm_txt(p))
        elif suf in {".trainzmesh", ".im", ".fbx", ".pm"}:
            reports.append(scan_mesh(p))
        elif name == "config.txt":
            reports.append(scan_config(p))
        elif suf in {".wav", ".wave", ".mp3", ".ogg", ".flac"}:
            reports.append(scan_sound(p))
        else:
            reports.append(
                VeReport(
                    path=p,
                    findings=[
                        VeFinding(
                            0, "info", p, "no VE rules for this file type", False
                        )
                    ],
                )
            )
    return reports
