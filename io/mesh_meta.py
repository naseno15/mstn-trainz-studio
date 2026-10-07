"""Trainz mesh metadata (.txt next to mesh) — materials / two-sided."""
from __future__ import annotations

import re
from pathlib import Path

# Sibling meta is ``mesh.fbx`` → ``mesh.txt`` (not config.txt / *.texture.txt).
_SKIP_META_NAMES = frozenset({"config.txt"})


def mesh_meta_path(mesh_path: Path) -> Path:
    """Canonical metadata path beside a mesh file (Trainz wiki naming)."""
    mesh_path = Path(mesh_path)
    return mesh_path.parent / f"{mesh_path.stem}.txt"


def find_mesh_meta(mesh_path: Path | None) -> Path | None:
    """Return existing sibling metadata .txt, or None."""
    if mesh_path is None:
        return None
    path = mesh_meta_path(Path(mesh_path))
    if not path.is_file():
        return None
    if path.name.lower() in _SKIP_META_NAMES:
        return None
    if path.name.lower().endswith(".texture.txt"):
        return None
    return path


def _find_matching_brace(text: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_block(text: str, key: str) -> tuple[str, int, int] | None:
    """Return (inner, open_brace_index, close_brace_index) for ``key { ... }``."""
    pattern = re.compile(r"\b" + re.escape(key) + r"\b\s*\{", flags=re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    open_pos = text.find("{", match.start())
    if open_pos < 0:
        return None
    close_pos = _find_matching_brace(text, open_pos)
    if close_pos < 0:
        return None
    return text[open_pos + 1 : close_pos], open_pos, close_pos


def _top_level_blocks(inner: str) -> list[tuple[str, str, int, int]]:
    """Parse ``name { body }`` entries; return (name, body, start, end) in inner."""
    out: list[tuple[str, str, int, int]] = []
    i = 0
    n = len(inner)
    while i < n:
        while i < n and inner[i].isspace():
            i += 1
        if i >= n:
            break
        name_start = i
        while i < n and inner[i] not in "{":
            i += 1
        if i >= n:
            break
        name = inner[name_start:i].strip().strip('"')
        open_pos = i
        close_pos = _find_matching_brace(inner, open_pos)
        if close_pos < 0:
            break
        body = inner[open_pos + 1 : close_pos]
        out.append((name, body, name_start, close_pos + 1))
        i = close_pos + 1
    return out


def parse_two_sided_map(text: str) -> dict[str, bool]:
    """``material name → two-sided`` from a mesh metadata file body."""
    block = _extract_block(text, "materials")
    if block is None:
        return {}
    inner, _, _ = block
    out: dict[str, bool] = {}
    for name, body, _, _ in _top_level_blocks(inner):
        if not name:
            continue
        m = re.search(
            r"\btwo-sided\s+([01]|true|false|yes|no)\b",
            body,
            flags=re.IGNORECASE,
        )
        if m:
            out[name] = m.group(1).lower() in {"1", "true", "yes"}
    return out


def _replace_two_sided_in_body(body: str, on: bool) -> str:
    flag = "1" if on else "0"
    new_line = f"two-sided {flag}"
    if re.search(r"\btwo-sided\s+", body, flags=re.IGNORECASE):
        return re.sub(
            r"\btwo-sided\s+([01]|true|false|yes|no)\b",
            new_line,
            body,
            count=1,
            flags=re.IGNORECASE,
        )
    trimmed = body.rstrip()
    if trimmed and not trimmed.endswith("\n"):
        trimmed += "\n"
    # indent like typical Trainz meta
    return trimmed + f"    {new_line}\n"


def set_material_two_sided(text: str, material: str, on: bool) -> str:
    """Upsert ``materials { material { two-sided 0|1 } }``; preserve other tags."""
    material = (material or "").strip()
    if not material:
        return text
    flag = "1" if on else "0"
    materials = _extract_block(text, "materials")
    if materials is None:
        stub = (
            f"materials\n"
            f"{{\n"
            f"  {material}\n"
            f"  {{\n"
            f"    two-sided {flag}\n"
            f"  }}\n"
            f"}}\n"
        )
        body = text.rstrip()
        if body:
            body += "\n\n"
        return body + stub

    inner, open_pos, close_pos = materials
    blocks = _top_level_blocks(inner)
    target_i = next(
        (i for i, (n, _, _, _) in enumerate(blocks) if n.lower() == material.lower()),
        -1,
    )
    if target_i >= 0:
        name, body, b_start, b_end = blocks[target_i]
        new_body = _replace_two_sided_in_body(body, on)
        new_inner = inner[:b_start] + f"{name}\n  {{\n{new_body}  }}\n" + inner[b_end:]
    else:
        addition = f"  {material}\n  {{\n    two-sided {flag}\n  }}\n"
        new_inner = inner.rstrip() + ("\n" if inner.strip() else "") + addition
    return text[: open_pos + 1] + new_inner + text[close_pos:]


def read_two_sided(meta_path: Path | None, material: str) -> bool | None:
    """Return two-sided for material, or None if unset / missing file."""
    if meta_path is None or not material:
        return None
    path = Path(meta_path)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    mapping = parse_two_sided_map(text)
    for name, val in mapping.items():
        if name.lower() == material.lower():
            return val
    return None


def write_two_sided_map(meta_path: Path, flags: dict[str, bool]) -> Path:
    """Upsert each material's own ``two-sided`` flag in one file write."""
    path = Path(meta_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        text = ""
    for material, on in flags.items():
        text = set_material_two_sided(text, material, bool(on))
    path.write_text(text, encoding="utf-8")
    return path


def write_two_sided_many(meta_path: Path, materials: list[str], on: bool) -> Path:
    """Upsert ``two-sided`` for each material name in one file write."""
    return write_two_sided_map(meta_path, {name: on for name in materials})


def write_two_sided(meta_path: Path, material: str, on: bool) -> Path:
    """Create/update mesh metadata so ``material`` has ``two-sided``."""
    return write_two_sided_many(meta_path, [material], on)


def apply_meta_two_sided_to_parts(
    parts: list,
    meta_path: Path | None,
    *,
    default: bool = False,
) -> int:
    """Set ``part.two_sided`` from metadata by matching ``part.name``.

    Missing / empty meta → every part gets ``default`` (False).
    Returns how many parts got an explicit meta value.
    """
    if meta_path is None or not Path(meta_path).is_file():
        for p in parts:
            p.two_sided = default
        return 0
    try:
        text = Path(meta_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        for p in parts:
            p.two_sided = default
        return 0
    mapping = parse_two_sided_map(text)
    lower = {k.lower(): v for k, v in mapping.items()}
    n = 0
    for p in parts:
        name = (getattr(p, "name", "") or "").strip()
        if not name:
            p.two_sided = default
            continue
        if name.lower() in lower:
            p.two_sided = lower[name.lower()]
            n += 1
            continue
        # family-ish: meta key without .m.* suffix
        base = name.split(".m.", 1)[0].lower()
        hit = next(
            (v for k, v in lower.items() if k == base or k.startswith(base + ".")),
            None,
        )
        if hit is not None:
            p.two_sided = hit
            n += 1
        else:
            p.two_sided = default
    return n
