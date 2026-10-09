"""Export trainz_studio (Python) UI catalogs to assets/i18n/<lang>.json for the C++ port.

Merges cpp_<lang>.json (strings only the C++ UI has) on top. Re-run after editing either side.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_I18N = ROOT.parent / "trainz_studio" / "ui" / "i18n"
OUT = ROOT / "assets" / "i18n"


def load_strings(lang: str) -> dict[str, str]:
    scope: dict = {}
    exec(compile((PY_I18N / f"catalog_{lang}.py").read_text(encoding="utf-8"), str(PY_I18N), "exec"), scope)
    return dict(scope["STRINGS"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in ("th", "ja", "id"):
        strings = load_strings(lang)
        extra = OUT / f"cpp_{lang}.json"
        if extra.is_file():
            strings.update(json.loads(extra.read_text(encoding="utf-8")))
        (OUT / f"{lang}.json").write_text(json.dumps(strings, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        print(lang, len(strings))


if __name__ == "__main__":
    main()
