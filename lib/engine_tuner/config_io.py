"""Parse and write Trainz engine config.txt files."""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .throttle_round import fmt_config, normalize_points


@dataclass
class EngineConfig:
    header: dict[str, Any] = field(default_factory=dict)
    flowsize: dict[str, float] = field(default_factory=dict)
    volume: dict[str, float] = field(default_factory=dict)
    pressure: dict[str, float] = field(default_factory=dict)
    mass: dict[str, float] = field(default_factory=dict)
    motor: dict[str, float] = field(default_factory=dict)
    throttle_power: dict[int, list[tuple[float, float]]] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None

    def clone(self) -> "EngineConfig":
        return deepcopy(self)


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def _coerce(token: str) -> Any:
    if _is_number(token):
        return float(token)
    return token


def _first_token(line: str) -> str:
    return line.strip().split()[0] if line.strip() else ""


def _line_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped in {"{", "}"}:
        return None
    return stripped.split()[0]


def _parse_quoted_value(lines: list[str], start_idx: int, first_line: str) -> tuple[str, int]:
    """Return (string value, next index)."""
    m = re.search(r'"', first_line)
    if not m:
        return first_line.strip(), start_idx + 1
    after = first_line[first_line.index('"') + 1 :]
    if after.endswith('"') and not after.endswith('\\"'):
        return after[:-1], start_idx + 1
    chunks = [after]
    idx = start_idx + 1
    while idx < len(lines):
        chunk = lines[idx]
        if chunk.rstrip().endswith('"'):
            chunks.append(chunk.rstrip()[:-1])
            return "\n".join(chunks), idx + 1
        chunks.append(chunk)
        idx += 1
    return "\n".join(chunks), idx


def _parse_kv_line(line: str) -> tuple[str, Any] | None:
    stripped = line.strip()
    if not stripped or stripped in {"{", "}"}:
        return None
    parts = stripped.split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    key, rest = parts[0], parts[1].strip()
    if rest == "{":
        return key, "{"
    if rest.startswith('"'):
        if rest.endswith('"') and rest.count('"') >= 2:
            return key, rest.strip('"')
        return key, rest  # multiline handled elsewhere
    tok = rest.split()[0]
    return key, _coerce(tok)


def _parse_block(lines: list[str], idx: int) -> tuple[dict[str, Any], int]:
    """idx points at line containing '{'."""
    block: dict[str, Any] = {}
    idx += 1
    while idx < len(lines):
        line = lines[idx]
        token = line.strip()
        if token == "}":
            return block, idx + 1
        if not token:
            idx += 1
            continue
        if token == "{":
            idx += 1
            continue
        kv = _parse_kv_line(line)
        if kv is None:
            idx += 1
            continue
        key, value = kv
        if value == "{":
            nested, idx = _parse_block(lines, idx)
            block[key] = nested
            continue
        if value is None:
            nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            if nxt == "{":
                nested, idx = _parse_block(lines, idx + 1)
                block[key] = nested
            else:
                idx += 1
            continue
        if isinstance(value, str) and value.startswith('"'):
            text, idx = _parse_quoted_value(lines, idx, line)
            block[key] = text
            continue
        block[key] = value
        idx += 1
    return block, idx


def parse_config_text(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    root: dict[str, Any] = {}
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        idx += 1
        if not stripped:
            continue
        if stripped == "{":
            continue
        if stripped.endswith("{"):
            key = stripped[:-1].strip()
            value, idx = _parse_block(lines, idx - 1)
            root[key] = value
            continue
        kv = _parse_kv_line(line)
        if kv is None:
            continue
        key, value = kv
        if value is None:
            nxt = lines[idx].strip() if idx < len(lines) else ""
            if nxt == "{":
                nested, idx = _parse_block(lines, idx)
                root[key] = nested
            else:
                continue
            continue
        if value == "{":
            nested, idx = _parse_block(lines, idx - 1)
            root[key] = nested
            continue
        if isinstance(value, str) and ('"' in line):
            text_val, idx = _parse_quoted_value(lines, idx - 1, line)
            root[key] = text_val
            continue
        root[key] = value
    return root


def _throttle_from_tree(raw: dict[str, Any] | None) -> dict[int, list[tuple[float, float]]]:
    out: dict[int, list[tuple[float, float]]] = {}
    if not raw:
        return out
    for notch_key, block in raw.items():
        try:
            notch = int(notch_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(block, dict):
            continue
        pairs: list[tuple[float, float]] = []
        for speed_key, te in block.items():
            try:
                speed = float(speed_key)
                force = float(te)
            except (TypeError, ValueError):
                continue
            pairs.append((speed, force))
        out[notch] = normalize_points(pairs)
    return out


def _throttle_to_tree(curves: dict[int, list[tuple[float, float]]]) -> dict[str, dict[str, str]]:
    tree: dict[str, dict[str, str]] = {}
    for notch in sorted(curves):
        block: dict[str, str] = {}
        for speed, te in sorted(curves[notch], key=lambda p: p[0]):
            block[fmt_config(speed)] = fmt_config(te)
        tree[str(notch)] = block
    return tree


def _float_dict(raw: dict[str, Any] | None) -> dict[str, float]:
    if not raw:
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def load_config_from_text(text: str, *, source_path: str | None = None) -> EngineConfig:
    """Parse enginespec config.txt body (shared by disk open + CDP session)."""
    tree = parse_config_text(text)
    known_blocks = {"flowsize", "volume", "pressure", "mass", "motor", "throttle-power"}
    cfg = EngineConfig(
        header={k: v for k, v in tree.items() if k not in known_blocks},
        flowsize=_float_dict(tree.get("flowsize")),
        volume=_float_dict(tree.get("volume")),
        pressure=_float_dict(tree.get("pressure")),
        mass=_float_dict(tree.get("mass")),
        motor=_float_dict(tree.get("motor")),
        throttle_power=_throttle_from_tree(tree.get("throttle-power")),
        source_path=source_path,
    )
    for key in ("dynamic-brake", "thumbnails", "kuid-table"):
        if key in tree:
            cfg.extras[key] = tree[key]
    return cfg


def looks_like_enginespec(text: str) -> bool:
    """True if config text matches Engine Tuner template (kind or throttle curves)."""
    try:
        tree = parse_config_text(text or "")
    except Exception:
        return False
    kind = str(tree.get("kind", "")).strip().strip('"').lower()
    if kind == "enginespec":
        return True
    return isinstance(tree.get("throttle-power"), dict) and bool(tree.get("throttle-power"))


def load_config(path: str | Path) -> EngineConfig:
    path = Path(path)
    return load_config_from_text(
        path.read_text(encoding="utf-8", errors="replace"),
        source_path=str(path),
    )


def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_scalar(key: str, value: Any) -> str:
    if isinstance(value, str) and ("\n" in value or " " in value.strip()):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key:<40}"{escaped}"'
    if isinstance(value, float):
        return f"{key:<40}{_fmt(value)}"
    return f"{key:<40}{value}"


def _format_block(name: str, block: dict[str, Any], indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines = [f"{pad}{name}", f"{pad}{{"]
    for key, value in block.items():
        if isinstance(value, dict):
            lines.extend(_format_block(str(key), value, indent + 1))
        else:
            if isinstance(value, float):
                val = _fmt(value)
            else:
                val = str(value)
            lines.append(f"{pad}  {str(key):<38}{val}")
    lines.append(f"{pad}}}")
    return lines


def config_to_text(cfg: EngineConfig) -> str:
    tree: dict[str, Any] = dict(cfg.header)
    tree["flowsize"] = cfg.flowsize
    tree["volume"] = cfg.volume
    tree["pressure"] = cfg.pressure
    tree["mass"] = cfg.mass
    tree["motor"] = cfg.motor
    tree["throttle-power"] = _throttle_to_tree(cfg.throttle_power)
    tree.update(cfg.extras)

    order = [
        "username",
        "category-region",
        "category-era",
        "kind",
        "author",
        "license",
        "trainz-build",
        "category-class",
        "description",
        "flowsize",
        "volume",
        "pressure",
        "mass",
        "motor",
        "throttle-power",
        "dynamic-brake",
        "thumbnails",
        "kuid",
        "kuid-table",
    ]

    lines: list[str] = [""]
    seen: set[str] = set()
    for key in order:
        if key not in tree:
            continue
        seen.add(key)
        val = tree[key]
        if isinstance(val, dict):
            lines.extend(_format_block(key, val))
            lines.append("")
        else:
            lines.append(_format_scalar(key, val))
            lines.append("")

    for key, val in tree.items():
        if key in seen:
            continue
        if isinstance(val, dict):
            lines.extend(_format_block(key, val))
            lines.append("")
        else:
            lines.append(_format_scalar(key, val))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def save_config(cfg: EngineConfig, path: str | Path) -> None:
    Path(path).write_text(config_to_text(cfg), encoding="utf-8")
