"""Add / improve HOME hub strings in all locale catalogs."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# English key → locale value
HOME: dict[str, dict[str, str]] = {
    "en": {
        "MSTN Trainz Studio": "MSTN Trainz Studio",
        "Meshes · sounds · engine · assets": "Meshes · sounds · engine · assets",
        "Mesh Studio": "Mesh Studio",
        ".trainzmesh / .im / FBX\nPreview · attachments · lamps": (
            ".trainzmesh / .im / FBX\nPreview · attachments · lamps"
        ),
        "Sounds Studio": "Sounds Studio",
        "Loop QC · track→track\nWaveform · Fix · export": (
            "Loop QC · track→track\nWaveform · Fix · export"
        ),
        "Engine Tuner": "Engine Tuner",
        "enginespec curves\nThrottle TE · sim preview": (
            "enginespec curves\nThrottle TE · sim preview"
        ),
        "Assets Tools": "Assets Tools",
        "CDP/TZarc · texture.txt · LM\nKUID hash — native writers": (
            "CDP/TZarc · texture.txt · LM\nKUID hash — native writers"
        ),
        "Open  →": "Open  →",
        "Drop files": "Drop files",
        "Copyright MSTN Production": "Copyright MSTN Production",
    },
    "th": {
        "MSTN Trainz Studio": "MSTN Trainz Studio",
        "Meshes · sounds · engine · assets": "เมช · เสียง · เครื่องยนต์ · แอสเซ็ต",
        "Mesh Studio": "Mesh Studio",
        ".trainzmesh / .im / FBX\nPreview · attachments · lamps": (
            ".trainzmesh / .im / FBX\nพรีวิว · จุดยึด · ไฟ"
        ),
        "Sounds Studio": "Sounds Studio",
        "Loop QC · track→track\nWaveform · Fix · export": (
            "ตรวจลูป · แทร็ก→แทร็ก\nเวฟฟอร์ม · แก้ · ส่งออก"
        ),
        "Engine Tuner": "Engine Tuner",
        "enginespec curves\nThrottle TE · sim preview": (
            "เส้นโค้ง enginespec\nแรงดึงคันเร่ง · พรีวิวจำลอง"
        ),
        "Assets Tools": "Assets Tools",
        "CDP/TZarc · texture.txt · LM\nKUID hash — native writers": (
            "CDP/TZarc · texture.txt · LM\nแฮช KUID — เขียนไฟล์ในตัว"
        ),
        "Open  →": "เปิด  →",
        "Drop files": "วางไฟล์",
        "Copyright MSTN Production": "ลิขสิทธิ์ MSTN Production",
    },
    "ja": {
        "MSTN Trainz Studio": "MSTN Trainz Studio",
        "Meshes · sounds · engine · assets": "メッシュ · サウンド · エンジン · アセット",
        "Mesh Studio": "Mesh Studio",
        ".trainzmesh / .im / FBX\nPreview · attachments · lamps": (
            ".trainzmesh / .im / FBX\nプレビュー · アタッチメント · ランプ"
        ),
        "Sounds Studio": "Sounds Studio",
        "Loop QC · track→track\nWaveform · Fix · export": (
            "ループQC · トラック→トラック\n波形 · 修正 · 書き出し"
        ),
        "Engine Tuner": "Engine Tuner",
        "enginespec curves\nThrottle TE · sim preview": (
            "enginespec カーブ\nスロットルTE · シミュレビュー"
        ),
        "Assets Tools": "Assets Tools",
        "CDP/TZarc · texture.txt · LM\nKUID hash — native writers": (
            "CDP/TZarc · texture.txt · LM\nKUIDハッシュ — 内蔵ライター"
        ),
        "Open  →": "開く  →",
        "Drop files": "ファイルをドロップ",
        "Copyright MSTN Production": "Copyright MSTN Production",
    },
    "id": {
        "MSTN Trainz Studio": "MSTN Trainz Studio",
        "Meshes · sounds · engine · assets": "Mesh · suara · mesin · aset",
        "Mesh Studio": "Mesh Studio",
        ".trainzmesh / .im / FBX\nPreview · attachments · lamps": (
            ".trainzmesh / .im / FBX\nPratinjau · attachment · lampu"
        ),
        "Sounds Studio": "Sounds Studio",
        "Loop QC · track→track\nWaveform · Fix · export": (
            "Loop QC · trek→trek\nGelombang · Perbaiki · ekspor"
        ),
        "Engine Tuner": "Engine Tuner",
        "enginespec curves\nThrottle TE · sim preview": (
            "kurva enginespec\nThrottle TE · pratinjau sim"
        ),
        "Assets Tools": "Assets Tools",
        "CDP/TZarc · texture.txt · LM\nKUID hash — native writers": (
            "CDP/TZarc · texture.txt · LM\nHash KUID — penulis bawaan"
        ),
        "Open  →": "Buka  →",
        "Drop files": "Letakkan file",
        "Copyright MSTN Production": "Hak cipta MSTN Production",
    },
}


def _merge(path: Path, locale: str) -> None:
    mod: dict = {}
    exec(path.read_text(encoding="utf-8"), mod)
    strings = dict(mod["STRINGS"])
    gloss = dict(mod.get("GLOSSARY", {}))
    strings.update(HOME[locale])
    lines = [
        f'"""{locale} UI catalog."""',
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
    print(locale, "keys", len(strings))


def main() -> None:
    ns: dict = {}
    exec((ROOT / "keys_en.py").read_text(encoding="utf-8"), ns)
    keys = list(ns["KEYS"])
    for k in HOME["en"]:
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
        "STRINGS: dict[str, str] = {k: k for k in KEYS}\n"
        # ensure HOME keys win even if KEYS lag
        + "STRINGS.update({\n"
        + ",\n".join(f"    {k!r}: {v!r}" for k, v in HOME["en"].items())
        + ",\n})\n\n"
        "GLOSSARY: dict[str, str] = dict(_GLOSSARY)\n",
        encoding="utf-8",
    )
    for loc, name in (
        ("th", "catalog_th.py"),
        ("ja", "catalog_ja.py"),
        ("id", "catalog_id.py"),
    ):
        _merge(ROOT / name, loc)


if __name__ == "__main__":
    main()
