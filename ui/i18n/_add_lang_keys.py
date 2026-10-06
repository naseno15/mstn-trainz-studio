"""Add Lang-menu keys to catalogs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

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


def main() -> None:
    ns: dict = {}
    exec((ROOT / "keys_en.py").read_text(encoding="utf-8"), ns)
    keys = list(ns["KEYS"])
    for k in EXTRA["en"]:
        if k not in keys:
            keys.append(k)
    (ROOT / "keys_en.py").write_text(
        '"""Clean English UI keys for translation catalogs."""\n\nKEYS = [\n'
        + ",\n".join(f"    {k!r}" for k in keys)
        + ",\n]\n",
        encoding="utf-8",
    )
    (ROOT / "catalog_en.py").write_text(
        '"""English (en) UI catalog."""\n'
        "from __future__ import annotations\n\n"
        "from .glossary_ve import GLOSSARY as _GLOSSARY\n"
        "from .keys_en import KEYS\n\n"
        "STRINGS: dict[str, str] = {k: k for k in KEYS}\n\n"
        "GLOSSARY: dict[str, str] = dict(_GLOSSARY)\n",
        encoding="utf-8",
    )
    for loc, fname in (
        ("th", "catalog_th.py"),
        ("ja", "catalog_ja.py"),
        ("id", "catalog_id.py"),
    ):
        path = ROOT / fname
        mod: dict = {}
        exec(path.read_text(encoding="utf-8"), mod)
        strings = dict(mod["STRINGS"])
        gloss = dict(mod["GLOSSARY"])
        strings.update(EXTRA[loc])
        lines = [
            f'"""{loc} UI catalog."""',
            "from __future__ import annotations",
            "",
            "STRINGS: dict[str, str] = {",
        ]
        for k, v in strings.items():
            lines.append(f"    {k!r}: {v!r},")
        lines += ["}", "", "GLOSSARY: dict[str, str] = {"]
        for k, v in gloss.items():
            lines.append(f"    {k!r}: {v!r},")
        lines += ["}", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        print(loc, len(strings), len(gloss))
    print("en keys", len(keys))


if __name__ == "__main__":
    main()
