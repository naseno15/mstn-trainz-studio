"""VE / validation glossary — stable IDs for explanatory translations."""
from __future__ import annotations

# English baseline values; locale modules map these IDs to localized prose.

GLOSSARY: dict[str, str] = {
    "ve39.name": "VE39 — solid / near-uniform texture",
    "ve39.tip": (
        "Trainz Content Manager rejects textures that are effectively one flat color "
        "(validation VE39). Real albedo maps need visible variation — even subtle noise "
        "or a tiny pattern — so the engine does not treat the file as an invalid solid fill."
    ),
    "ve39.scan": (
        "Scan listed images for near-uniform RGBA (same as Packages Finder). "
        "Uniform hits show as VE39 with a hex swatch in the Status column."
    ),
    "ve39.fix": (
        "Fix uniform maps in-place: creates a one-time sibling .bak backup, then paints "
        "a few inverse-color dots so the map is no longer uniform. Non-uniform files are skipped."
    ),
    "ve39.fix.confirm": (
        "Fix uniform textures in-place for {n} file(s)?\n"
        "Writes sibling .bak once, then adds noise dots."
    ),
    "ve39.status.uniform": "VE39 {color_hex}",
    "ve39.result.fixed_dots": "fixed (dots)",
    "ve39.result.fixed_4x4": "fixed (4×4)",
    "ve39.result.skip": "not uniform (skip)",
    "ve39.result.not_found": "not found",
    "ve39.ui.drop_first": "Drop images into the list first.",
    "ve39.ui.title": "VE39",
    "ve39.ui.fix_title": "VE39 fix",
    "ve39.ui.scan_action": "VE39 scan",
    "ve39.ui.fix_action": "VE39 fix…",
}
