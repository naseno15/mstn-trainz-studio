"""Trainz mesh material name check + rename (FBX / .trainzmesh).

Trainz expects FBX / mesh material names like ``body.m.pbrmetal`` or
``lamp.m.onetex``. Common authoring mistakes: missing ``.m.<effect>``,
typos (``pbrmetl``), Blender ``.001`` duplicates, wrong case.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

# Name-side effects (what appears after ``.m.`` in the material name).
KNOWN_EFFECTS: tuple[str, ...] = (
    "pbrmetal",
    "pbrmetalmasked",
    "pbrmetaldetail",
    "pbrmetalspec",
    "onetex",
    "glass",
    "clutter",
    "foliage",
)

# Authoring aliases → canonical name effect.
_EFFECT_ALIASES: dict[str, str] = {
    "stdonetex": "onetex",
    "m.onetex": "onetex",
    "m.pbrmetal": "pbrmetal",
    "pbr": "pbrmetal",
    "metal": "pbrmetal",
    "one_tex": "onetex",
    "onetext": "onetex",
}

_BLENDER_DUP_RE = re.compile(r"^(?P<head>.+?)(?P<dup>\.\d{3})$")
_M_SPLIT_RE = re.compile(r"^(?P<stem>.+?)\.m\.(?P<effect>[A-Za-z0-9_]+)$", re.I)
_LOOSE_EFFECT_RE = re.compile(
    r"(?P<stem>[A-Za-z0-9_\-]+?)[._\-\s]*(?P<effect>"
    + "|".join(re.escape(e) for e in sorted(KNOWN_EFFECTS, key=len, reverse=True))
    + r")$",
    re.I,
)
_ASCII_MAT_RE = re.compile(
    r'Material:\s*"([^"]+)"\s*,\s*""\s*\{',
    re.I,
)
_ASCII_MAT_COLON_RE = re.compile(r"Material::([^\",\s]+)")
_NAME_TOKEN_RE = re.compile(rb"[A-Za-z0-9_\-]{1,96}\.m\.[A-Za-z0-9_]{2,32}")

_FBX_HEADER_LEN = 27
_FBX_NULL = b"\x00" * 13


@dataclass(frozen=True)
class MatNameIssue:
    name: str
    kind: str  # ok | missing_suffix | bad_effect | blender_dup | empty
    suggested: str | None
    detail: str

    @property
    def needs_fix(self) -> bool:
        return self.kind != "ok" and bool(self.suggested) and self.suggested != self.name


def normalize_effect(raw: str) -> str | None:
    """Map a typed effect / alias to a known name-side effect, or None."""
    key = (raw or "").strip().lower().replace(" ", "").replace("-", "")
    if not key:
        return None
    if key in _EFFECT_ALIASES:
        return _EFFECT_ALIASES[key]
    if key in KNOWN_EFFECTS:
        return key
    # fuzzy for short typos
    hits = get_close_matches(key, list(KNOWN_EFFECTS), n=1, cutoff=0.72)
    return hits[0] if hits else None


def check_mat_name(name: str) -> MatNameIssue:
    """Validate one Trainz material name; suggest a fix when possible."""
    raw = (name or "").strip()
    if not raw:
        return MatNameIssue("", "empty", None, "empty material name")

    # Strip Blender duplicate suffix first (``.001``) — keep checking the head.
    blender = _BLENDER_DUP_RE.match(raw)
    if blender and blender.group("dup"):
        head = blender.group("head")
        inner = check_mat_name(head)
        if inner.kind == "ok":
            return MatNameIssue(
                raw,
                "blender_dup",
                head,
                f"Blender duplicate suffix {blender.group('dup')} - strip to '{head}'",
            )
        if inner.suggested:
            return MatNameIssue(
                raw,
                "blender_dup",
                inner.suggested,
                f"Blender '{blender.group('dup')}' + {inner.detail}",
            )
        return MatNameIssue(
            raw,
            "blender_dup",
            head,
            f"Blender duplicate suffix {blender.group('dup')}",
        )

    m = _M_SPLIT_RE.match(raw)
    if m:
        stem = m.group("stem")
        effect_raw = m.group("effect")
        effect = normalize_effect(effect_raw)
        if effect is None:
            guess = get_close_matches(
                effect_raw.lower(), list(KNOWN_EFFECTS), n=1, cutoff=0.55
            )
            suggested = f"{stem}.m.{guess[0]}" if guess else f"{stem}.m.pbrmetal"
            tip = suggested.split(".m.", 1)[-1]
            return MatNameIssue(
                raw,
                "bad_effect",
                suggested,
                f"unknown effect '{effect_raw}' - try '{tip}'",
            )
        canon = f"{stem}.m.{effect}"
        if canon != raw:
            return MatNameIssue(
                raw,
                "bad_effect",
                canon,
                f"normalize '{effect_raw}' -> '{effect}'",
            )
        return MatNameIssue(raw, "ok", None, "ok")

    # Missing ``.m.`` — try to salvage stem + effect from loose naming.
    loose = _LOOSE_EFFECT_RE.match(raw.replace(" ", ""))
    if loose:
        stem = loose.group("stem").rstrip("._-")
        effect = normalize_effect(loose.group("effect")) or "pbrmetal"
        suggested = f"{stem}.m.{effect}"
        return MatNameIssue(
            raw,
            "missing_suffix",
            suggested,
            f"missing .m. - suggest '{suggested}'",
        )

    # Bare name → default pbrmetal (most common Trainz body shader).
    stem = re.sub(r"[^\w\-]+", "_", raw).strip("_") or "material"
    suggested = f"{stem}.m.pbrmetal"
    return MatNameIssue(
        raw,
        "missing_suffix",
        suggested,
        f"no .m.<effect> - suggest '{suggested}'",
    )


def list_materials(path: Path) -> list[str]:
    """Collect material names from ``.fbx`` / ``.trainzmesh`` (unique, stable order)."""
    path = Path(path)
    suf = path.suffix.lower()
    if suf == ".fbx":
        return _list_fbx_materials(path)
    if suf == ".trainzmesh":
        return _list_tzmf_materials(path)
    if suf == ".im":
        return _list_im_materials(path)
    return []


def scan_materials(path: Path) -> list[MatNameIssue]:
    """List + check every material in a mesh file."""
    names = list_materials(path)
    if not names:
        return []
    return [check_mat_name(n) for n in names]


def format_mat_report(path: Path, issues: list[MatNameIssue]) -> str:
    """Plain-text report for the Mesh Ops log pane."""
    lines = [f"— {Path(path).name} —"]
    if not issues:
        lines.append("(no Trainz material names found)")
        return "\n".join(lines)
    bad = [i for i in issues if i.needs_fix]
    ok_n = len(issues) - len(bad)
    lines.append(f"{len(issues)} material(s) | {ok_n} ok | {len(bad)} need fix")
    for iss in issues:
        if iss.kind == "ok":
            lines.append(f"  OK  {iss.name}")
            continue
        arrow = f" -> {iss.suggested}" if iss.suggested else ""
        lines.append(f"  !!  {iss.name}{arrow}")
        lines.append(f"      {iss.detail}")
    return "\n".join(lines)


def apply_renames(path: Path, mapping: dict[str, str], *, backup: bool = True) -> int:
    """Apply ``old → new`` material renames. Returns number of names changed."""
    path = Path(path)
    clean = {a: b for a, b in mapping.items() if a and b and a != b}
    if not clean:
        return 0
    suf = path.suffix.lower()
    if suf == ".fbx":
        return _rename_fbx_materials(path, clean, backup=backup)
    if suf == ".trainzmesh":
        return _rename_tzmf_materials(path, clean, backup=backup)
    raise ValueError(f"material rename not supported for {suf or path.name}")


def suggested_mapping(issues: list[MatNameIssue]) -> dict[str, str]:
    return {i.name: i.suggested for i in issues if i.needs_fix and i.suggested}


# ── extractors ──────────────────────────────────────────────


def _list_tzmf_materials(path: Path) -> list[str]:
    from .tzmf_edit import parse_materials

    mats = parse_materials(path.read_bytes())
    out: list[str] = []
    seen: set[str] = set()
    for m in mats:
        if m.name and m.name not in seen:
            seen.add(m.name)
            out.append(m.name)
    return out


def _list_im_materials(path: Path) -> list[str]:
    # Older .im rarely embeds ``*.m.*``; keep a soft string scrape.
    data = path.read_bytes()
    found = [m.decode("ascii", "replace") for m in _NAME_TOKEN_RE.findall(data)]
    out: list[str] = []
    seen: set[str] = set()
    for n in found:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _list_fbx_materials(path: Path) -> list[str]:
    data = path.read_bytes()
    if data.startswith(b"Kaydara FBX Binary"):
        return _list_fbx_binary_materials(data)
    text = data.decode("utf-8", errors="replace")
    names: list[str] = []
    seen: set[str] = set()
    for rx in (_ASCII_MAT_RE, _ASCII_MAT_COLON_RE):
        for m in rx.finditer(text):
            n = m.group(1).strip()
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    return names


def _list_fbx_binary_materials(data: bytes) -> list[str]:
    roots = _fbx_parse_roots(data)
    objs = next((n for n in roots if n.name == "Objects"), None)
    if objs is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for ch in objs.children:
        if ch.name != "Material":
            continue
        for kind, val in ch.props:
            if kind != "S":
                continue
            name = _fbx_decode_s(val)
            if name and name not in seen:
                seen.add(name)
                out.append(name)
            break
    return out


# ── renamers ────────────────────────────────────────────────


def _rename_tzmf_materials(
    path: Path, mapping: dict[str, str], *, backup: bool
) -> int:
    from .tzmf_edit import apply_material_edits, parse_materials, write_trainzmesh

    data = bytearray(path.read_bytes())
    mats = parse_materials(data)
    n = 0
    # high→low offsets so earlier string patches stay valid across renames
    work = sorted(
        ((m, mapping[m.name]) for m in mats if m.name in mapping),
        key=lambda pair: pair[0].name_off,
        reverse=True,
    )
    for mat, new_name in work:
        data = apply_material_edits(data, mat, name=new_name)
        n += 1
    if n:
        write_trainzmesh(path, data, backup=backup)
    return n


def _rename_fbx_materials(
    path: Path, mapping: dict[str, str], *, backup: bool
) -> int:
    data = path.read_bytes()
    if data.startswith(b"Kaydara FBX Binary"):
        new_data, n = _rename_fbx_binary(data, mapping)
        if n == 0:
            return 0
        if backup:
            bak = path.with_suffix(path.suffix + ".bak-mat")
            if not bak.is_file():
                bak.write_bytes(data)
        path.write_bytes(new_data)
        return n
    # ASCII FBX — replace Material definition names only.
    text = data.decode("utf-8", errors="replace")
    n = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal n
        old = match.group(1)
        new = mapping.get(old)
        if not new:
            return match.group(0)
        n += 1
        return match.group(0).replace(old, new, 1)

    text2 = _ASCII_MAT_RE.sub(_sub, text)
    text2 = _ASCII_MAT_COLON_RE.sub(
        lambda m: f"Material::{mapping[m.group(1)]}"
        if m.group(1) in mapping
        else m.group(0),
        text2,
    )
    # count colon replacements that _sub didn't see
    if text2 != text and n == 0:
        n = sum(1 for a, b in mapping.items() if a in text and b in text2)
    if n == 0 and text2 == text:
        return 0
    if backup:
        bak = path.with_suffix(path.suffix + ".bak-mat")
        if not bak.is_file():
            bak.write_bytes(data)
    path.write_text(text2, encoding="utf-8", newline="")
    return max(n, 1)


def _rename_fbx_binary(data: bytes, mapping: dict[str, str]) -> tuple[bytes, int]:
    roots = _fbx_parse_roots(data)
    n = 0
    for node in roots:
        n += _fbx_rename_in_tree(node, mapping)
    if n == 0:
        return data, 0
    ver = struct.unpack_from("<I", data, 23)[0]
    out = bytearray(data[:_FBX_HEADER_LEN])
    for node in roots:
        _fbx_write_node(out, node, ver)
    # trailing null record (end of root list)
    out.extend(_FBX_NULL)
    # preserve footer after original root null if present
    footer = _fbx_footer(data)
    if footer:
        out.extend(footer)
    return bytes(out), n


def _fbx_rename_in_tree(node: "_FbxNode", mapping: dict[str, str]) -> int:
    n = 0
    if node.name == "Material" and node.props:
        # First S property is the material display name.
        for i, (kind, val) in enumerate(node.props):
            if kind != "S":
                continue
            old = _fbx_decode_s(val)
            new = mapping.get(old)
            if new and new != old:
                node.props[i] = ("S", _fbx_encode_s(new, val))
                n += 1
            break
    for ch in node.children:
        n += _fbx_rename_in_tree(ch, mapping)
    return n


def _fbx_footer(data: bytes) -> bytes:
    """Bytes after the root-level null record (alignment / FOOT magic)."""
    off = _FBX_HEADER_LEN
    try:
        while off + 13 <= len(data):
            if data[off : off + 13] == _FBX_NULL:
                return data[off + 13 :]
            end_off = struct.unpack_from("<I", data, off)[0]
            if end_off <= off:
                break
            off = end_off
    except Exception:
        return b""
    return b""


# ── minimal FBX binary tree ─────────────────────────────────


@dataclass
class _FbxNode:
    name: str
    props: list[tuple[str, object]]
    children: list[_FbxNode]
    has_null_sentinel: bool = False


def _fbx_decode_s(raw: bytes | str) -> str:
    if isinstance(raw, str):
        return raw
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _fbx_encode_s(text: str, old_raw: bytes | str) -> bytes:
    """Keep trailing ``\\x00`` + padding style of the original S value when possible."""
    body = text.encode("utf-8")
    if isinstance(old_raw, bytes) and b"\x00" in old_raw:
        # common: name + \\0 + optional class pad
        parts = old_raw.split(b"\x00", 1)
        tail = b"\x00" + parts[1] if len(parts) > 1 else b"\x00"
        return body + (tail if tail.startswith(b"\x00") else b"\x00")
    return body + b"\x00"


def _fbx_parse_roots(data: bytes) -> list[_FbxNode]:
    if len(data) < _FBX_HEADER_LEN + 4:
        return []
    ver = struct.unpack_from("<I", data, 23)[0]
    if ver >= 7500:
        # ponytail: FBX 7500+ uses u64 offsets — rare for Trainz exports; skip rewrite
        raise ValueError(f"FBX version {ver} not supported for material rename (need <7500)")
    roots: list[_FbxNode] = []
    off = _FBX_HEADER_LEN
    while off + 13 <= len(data):
        if data[off : off + 13] == _FBX_NULL:
            break
        node, off = _fbx_read_node(data, off)
        if node is None:
            break
        roots.append(node)
    return roots


def _fbx_read_prop(buf: bytes, off: int) -> tuple[tuple[str, object], int]:
    t = buf[off : off + 1]
    off += 1
    if t == b"Y":
        return ("Y", struct.unpack_from("<h", buf, off)[0]), off + 2
    if t == b"C":
        return ("C", buf[off]), off + 1
    if t == b"I":
        return ("I", struct.unpack_from("<i", buf, off)[0]), off + 4
    if t == b"F":
        return ("F", struct.unpack_from("<f", buf, off)[0]), off + 4
    if t == b"D":
        return ("D", struct.unpack_from("<d", buf, off)[0]), off + 8
    if t == b"L":
        return ("L", struct.unpack_from("<q", buf, off)[0]), off + 8
    if t == b"S":
        n = struct.unpack_from("<I", buf, off)[0]
        off += 4
        raw = bytes(buf[off : off + n])
        return ("S", raw), off + n
    if t == b"R":
        n = struct.unpack_from("<I", buf, off)[0]
        off += 4
        return ("R", bytes(buf[off : off + n])), off + n
    if t in (b"f", b"d", b"l", b"i", b"b"):
        count, enc, clen = struct.unpack_from("<III", buf, off)
        off += 12
        es = {b"f": 4, b"d": 8, b"l": 8, b"i": 4, b"b": 1}[t]
        raw_len = clen if enc == 1 else count * es
        raw = bytes(buf[off : off + raw_len])
        return (t.decode("ascii"), (count, enc, clen, raw)), off + raw_len
    raise ValueError(f"unsupported FBX property type {t!r} @ {off - 1}")


def _fbx_read_node(buf: bytes, off: int) -> tuple[_FbxNode | None, int]:
    if buf[off : off + 13] == _FBX_NULL:
        return None, off + 13
    end_off, nprops, _props_len = struct.unpack_from("<III", buf, off)
    name_len = buf[off + 12]
    name = buf[off + 13 : off + 13 + name_len].decode("ascii", errors="replace")
    poff = off + 13 + name_len
    props: list[tuple[str, object]] = []
    for _ in range(nprops):
        prop, poff = _fbx_read_prop(buf, poff)
        props.append(prop)
    children: list[_FbxNode] = []
    coff = poff
    has_null = False
    while coff < end_off:
        if coff + 13 <= end_off and buf[coff : coff + 13] == _FBX_NULL:
            has_null = True
            coff += 13
            break
        child, coff = _fbx_read_node(buf, coff)
        if child is None:
            break
        children.append(child)
    return _FbxNode(name, props, children, has_null_sentinel=has_null), end_off


def _fbx_write_prop(out: bytearray, kind: str, val: object) -> None:
    if kind == "Y":
        out.append(ord("Y"))
        out.extend(struct.pack("<h", int(val)))  # type: ignore[arg-type]
        return
    if kind == "C":
        out.append(ord("C"))
        out.append(int(val) & 0xFF)  # type: ignore[arg-type]
        return
    if kind == "I":
        out.append(ord("I"))
        out.extend(struct.pack("<i", int(val)))  # type: ignore[arg-type]
        return
    if kind == "F":
        out.append(ord("F"))
        out.extend(struct.pack("<f", float(val)))  # type: ignore[arg-type]
        return
    if kind == "D":
        out.append(ord("D"))
        out.extend(struct.pack("<d", float(val)))  # type: ignore[arg-type]
        return
    if kind == "L":
        out.append(ord("L"))
        out.extend(struct.pack("<q", int(val)))  # type: ignore[arg-type]
        return
    if kind == "S":
        raw = val if isinstance(val, (bytes, bytearray)) else _fbx_encode_s(str(val), b"\x00")
        out.append(ord("S"))
        out.extend(struct.pack("<I", len(raw)))
        out.extend(raw)
        return
    if kind == "R":
        raw = bytes(val)  # type: ignore[arg-type]
        out.append(ord("R"))
        out.extend(struct.pack("<I", len(raw)))
        out.extend(raw)
        return
    if kind in ("f", "d", "l", "i", "b"):
        count, enc, clen, raw = val  # type: ignore[misc]
        out.append(ord(kind))
        out.extend(struct.pack("<III", count, enc, clen))
        out.extend(raw)
        return
    raise ValueError(f"cannot write FBX prop {kind}")


def _fbx_write_node(out: bytearray, node: _FbxNode, ver: int) -> None:
    start = len(out)
    # placeholder header
    out.extend(b"\x00" * 12)
    name_b = node.name.encode("ascii", errors="replace")
    out.append(len(name_b) & 0xFF)
    out.extend(name_b)
    props_start = len(out)
    for kind, val in node.props:
        _fbx_write_prop(out, kind, val)
    props_len = len(out) - props_start
    for ch in node.children:
        _fbx_write_node(out, ch, ver)
    if node.children or node.has_null_sentinel:
        out.extend(_FBX_NULL)
    end_off = len(out)
    struct.pack_into("<III", out, start, end_off, len(node.props), props_len)
