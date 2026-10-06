"""Filter noisy extract fragments → clean KEYS list."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ns: dict = {}
exec((ROOT / "_extract_en_keys.py").read_text(encoding="utf-8"), ns)
keys: list[str] = list(ns["KEYS"])

_PUNCT = re.compile(r"^[\s·×→—\-–/\(\)\{\}\[\]\|\.\,\:\;\=\+\*\?\!\"'`~%#@<>]+$")


def _ok(s: str) -> bool:
    s2 = s.strip()
    if len(s2) < 2:
        return False
    if _PUNCT.fullmatch(s2):
        return False
    # pure format crumbs
    if s2 in {"(", ")", "…", "...", "pt", "Hz", "kN", "kPa", "km/h", "m", "KUID"}:
        return False
    return True


good = [k for k in keys if _ok(k)]
# stable order, unique
seen: set[str] = set()
ordered: list[str] = []
for k in good:
    if k in seen:
        continue
    seen.add(k)
    ordered.append(k)

out = ROOT / "keys_en.py"
lines = [
    '"""Clean English UI keys for translation catalogs."""',
    "",
    "KEYS = [",
]
lines.extend(f"    {k!r}," for k in ordered)
lines.append("]")
lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {len(ordered)} keys -> {out}")
