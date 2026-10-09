"""List UI strings the C++ port shows that the exported catalogs do not translate yet.

Sources: qsTr("…") literals in ui/qml, UI-looking QStringLiteral("…") in src/ui, and an optional
runtime harvest (TS_I18N_HARVEST=<file>). Writes assets/i18n/_missing.json (sorted list).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "assets" / "i18n"
QSTR = re.compile(r'qsTr\("((?:[^"\\]|\\.)*)"\)')
CPP = re.compile(r'QStringLiteral\("((?:[^"\\]|\\.)*)"\)')


def unescape(s: str) -> str:
    return json.loads(f'"{s}"')


def ui_like(s: str) -> bool:
    t = s.strip()
    if len(t) < 2 or not re.search(r"[A-Za-z]", t):
        return False
    if re.search(r"[_\\{}<>$=]|^[a-z][A-Za-z0-9]*$|^\.|://|^#|%\d|\.(png|qml|json|txt|exe|gs)$", t):
        return False
    return t[0].isupper() or " " in t or t[0] in "(…·—" or t.endswith("…")


def main() -> None:
    found: set[str] = set()
    for p in (ROOT / "ui" / "qml").glob("*.qml"):
        found.update(unescape(m) for m in QSTR.findall(p.read_text(encoding="utf-8")))
    for p in (ROOT / "src" / "ui").glob("*.cpp"):
        for m in CPP.findall(p.read_text(encoding="utf-8", errors="ignore")):
            text = unescape(m)
            if ui_like(text):
                found.add(text)
    for extra in sys.argv[1:]:
        found.update(json.loads(Path(extra).read_text(encoding="utf-8")).keys())
    have = json.loads((I18N / "th.json").read_text(encoding="utf-8"))
    missing = sorted(s for s in found if s not in have and re.search(r"[A-Za-z]", s))
    (I18N / "_missing.json").write_text(json.dumps(missing, ensure_ascii=False, indent=0), encoding="utf-8")
    print(len(found), "found ·", len(missing), "missing")


if __name__ == "__main__":
    main()
