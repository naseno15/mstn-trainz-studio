"""Merge cpp_<lang>.json overlays onto assets/i18n/<lang>.json.

The Python trainz_studio catalogs are gone; edit the JSON catalogs directly,
then re-run this after changing a cpp_*.json overlay.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "i18n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in ("th", "ja", "id"):
        path = OUT / f"{lang}.json"
        strings = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        extra = OUT / f"cpp_{lang}.json"
        if extra.is_file():
            strings.update(json.loads(extra.read_text(encoding="utf-8")))
        path.write_text(
            json.dumps(strings, ensure_ascii=False, indent=0, sort_keys=True),
            encoding="utf-8",
        )
        print(lang, len(strings))


if __name__ == "__main__":
    main()
