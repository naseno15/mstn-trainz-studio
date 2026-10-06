"""Add Lang-menu + font tip keys to all catalogs."""
from __future__ import annotations

from pathlib import Path

EXTRA: dict[str, dict[str, str]] = {
    "en": {
        "Lang": "Lang",
        "Switch UI language — menus, buttons, tooltips, and status codes.": (
            "Switch UI language — menus, buttons, tooltips, and status codes."
        ),
        "English — default UI language": "English — default UI language",
        "Thai — Noto Sans Thai Looped": "Thai — Noto Sans Thai Looped",
        "Japanese — Noto Sans CJK JP": "Japanese — Noto Sans CJK JP",
        "Indonesian — Noto Sans": "Indonesian — Noto Sans",
    },
    "th": {
        "Lang": "ภาษา",
        "Switch UI language — menus, buttons, tooltips, and status codes.": (
            "เปลี่ยนภาษาของอินเทอร์เฟซ — เมนู ปุ่ม คำอธิบาย และรหัสสถานะ"
        ),
        "English — default UI language": "อังกฤษ — ภาษาเริ่มต้นของอินเทอร์เฟซ",
        "Thai — Noto Sans Thai Looped": "ไทย — Noto Sans Thai Looped",
        "Japanese — Noto Sans CJK JP": "ญี่ปุ่น — Noto Sans CJK JP",
        "Indonesian — Noto Sans": "อินโดนีเซีย — Noto Sans",
    },
    "ja": {
        "Lang": "言語",
        "Switch UI language — menus, buttons, tooltips, and status codes.": (
            "UI言語を切り替え — メニュー、ボタン、ツールチップ、ステータスコード"
        ),
        "English — default UI language": "英語 — デフォルトのUI言語",
        "Thai — Noto Sans Thai Looped": "タイ語 — Noto Sans Thai Looped",
        "Japanese — Noto Sans CJK JP": "日本語 — Noto Sans CJK JP",
        "Indonesian — Noto Sans": "インドネシア語 — Noto Sans",
    },
    "id": {
        "Lang": "Bahasa",
        "Switch UI language — menus, buttons, tooltips, and status codes.": (
            "Ganti bahasa antarmuka — menu, tombol, tip, dan kode status"
        ),
        "English — default UI language": "Inggris — bahasa UI bawaan",
        "Thai — Noto Sans Thai Looped": "Thai — Noto Sans Thai Looped",
        "Japanese — Noto Sans CJK JP": "Jepang — Noto Sans CJK JP",
        "Indonesian — Noto Sans": "Indonesia — Noto Sans",
    },
}


def _patch(path: Path, locale: str) -> None:
    text = path.read_text(encoding="utf-8")
    # Ensure STRINGS dict gets new entries before closing brace of STRINGS
    marker = "\n}\n\nGLOSSARY:"
    if marker not in text:
        marker = "\n}\n\nGLOSSARY ="
    if marker not in text:
        raise SystemExit(f"cannot find STRINGS end in {path}")
    extras = EXTRA[locale]
    lines = []
    for k, v in extras.items():
        if repr(k) in text or f'"{k}"' in text:
            # still update via rewrite of whole extras block — skip if key literal present
            if f"{k!r}:" in text or f'"{k}":' in text:
                continue
        lines.append(f"    {k!r}: {v!r},")
    if not lines:
        print(f"{path.name}: already has extras")
        return
    insert = "\n".join(lines) + "\n"
    text = text.replace(marker, "\n" + insert + marker.lstrip("\n"), 1)
    path.write_text(text, encoding="utf-8")
    print(f"{path.name}: +{len(lines)}")


def main() -> None:
    root = Path(__file__).resolve().parent
    for loc, name in (
        ("en", "catalog_en.py"),
        ("th", "catalog_th.py"),
        ("ja", "catalog_ja.py"),
        ("id", "catalog_id.py"),
    ):
        _patch(root / name, loc)
    # also append to keys_en.py KEYS list
    keys_path = root / "keys_en.py"
    keys_text = keys_path.read_text(encoding="utf-8")
    added = 0
    for k in EXTRA["en"]:
        if repr(k) not in keys_text:
            keys_text = keys_text.rstrip() + f"\n    {k!r},\n]\n"
            # fix accidental double ]
            keys_text = keys_text.replace(",\n]\n]\n", ",\n]\n")
            if keys_text.count("\n]") > 1:
                # rebuild append properly
                pass
            added += 1
    # safer: rebuild KEYS append
    ns: dict = {}
    exec(keys_path.read_text(encoding="utf-8"), ns)
    keys = list(ns["KEYS"])
    for k in EXTRA["en"]:
        if k not in keys:
            keys.append(k)
            added += 1
    body = '"""Clean English UI keys for translation catalogs."""\n\nKEYS = [\n'
    body += ",\n".join(f"    {k!r}" for k in keys)
    body += ",\n]\n"
    keys_path.write_text(body, encoding="utf-8")
    # catalog_en identity map refresh
    en_path = root / "catalog_en.py"
    en_path.write_text(
        '"""English (en) UI catalog — identity mapping; English source strings are the keys."""\n'
        "from __future__ import annotations\n\n"
        "from .glossary_ve import GLOSSARY as _GLOSSARY\n"
        "from .keys_en import KEYS\n\n"
        "STRINGS: dict[str, str] = {k: k for k in KEYS}\n\n"
        "GLOSSARY: dict[str, str] = dict(_GLOSSARY)\n"
        # keep extras that might not be in KEYS yet — already in KEYS now
        ,
        encoding="utf-8",
    )
    # re-patch th/ja/id after en rewrite (en is fine)
    for loc, name in (("th", "catalog_th.py"), ("ja", "catalog_ja.py"), ("id", "catalog_id.py")):
        _patch(root / name, loc)
    print("keys added", added)


if __name__ == "__main__":
    main()
