"""English (en) UI catalog."""
from __future__ import annotations

from .glossary_ve import GLOSSARY as _GLOSSARY
from .keys_en import KEYS

STRINGS: dict[str, str] = {k: k for k in KEYS}
STRINGS.update({
    'MSTN Trainz Studio': 'MSTN Trainz Studio',
    'Meshes · sounds · engine · assets': 'Meshes · sounds · engine · assets',
    'Mesh Studio': 'Mesh Studio',
    '.trainzmesh / .im / FBX\nPreview · attachments · lamps': '.trainzmesh / .im / FBX\nPreview · attachments · lamps',
    'Sounds Studio': 'Sounds Studio',
    'Loop QC · track→track\nWaveform · Fix · export': 'Loop QC · track→track\nWaveform · Fix · export',
    'Engine Tuner': 'Engine Tuner',
    'enginespec curves\nThrottle TE · sim preview': 'enginespec curves\nThrottle TE · sim preview',
    'Assets Tools': 'Assets Tools',
    'CDP/TZarc · texture.txt · LM\nKUID hash — native writers': 'CDP/TZarc · texture.txt · LM\nKUID hash — native writers',
    'Open  →': 'Open  →',
    'Drop files': 'Drop files',
    'Copyright MSTN Production': 'Copyright MSTN Production',
})

GLOSSARY: dict[str, str] = dict(_GLOSSARY)
