"""Bump a few Indonesian menu labels that were left as English."""
from __future__ import annotations

from pathlib import Path

path = Path(__file__).resolve().parent / "catalog_id.py"
text = path.read_text(encoding="utf-8")
repl = {
    "'File': 'File'": "'File': 'Berkas'",
    "'Edit': 'Edit'": "'Edit': 'Sunting'",
    "'View': 'View'": "'View': 'Tampilan'",
    "'Open…': 'Open…'": "'Open…': 'Buka…'",
    "'Quit': 'Quit'": "'Quit': 'Keluar'",
    "'Undo': 'Undo'": "'Undo': 'Urungkan'",
    "'Redo': 'Redo'": "'Redo': 'Ulangi'",
    "'Home': 'Home'": "'Home': 'Beranda'",
    "'Settings…': 'Settings…'": "'Settings…': 'Pengaturan…'",
    "'Save Project': 'Save Project'": "'Save Project': 'Simpan Proyek'",
    "'Open Project…': 'Open Project…'": "'Open Project…': 'Buka Proyek…'",
    "'Reset camera': 'Reset camera'": "'Reset camera': 'Atur ulang kamera'",
}
n = 0
for a, b in repl.items():
    if a in text:
        text = text.replace(a, b, 1)
        n += 1
    else:
        print("miss", a)
path.write_text(text, encoding="utf-8")
print("fixed", n)
