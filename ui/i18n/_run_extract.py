"""Generate _extract_en_keys.py from ui/ + GUI-facing io/ strings."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"
OUT_KEYS = Path(__file__).resolve().parent / "_extract_en_keys.py"
OUT_GLOSS = Path(__file__).resolve().parent / "glossary_ve.py"

IO_FILES = [ROOT / "io" / "ve39.py"]

SKIP_FILES = {
    "ui/theme.py",
    "ui/i18n/_run_extract.py",
    "ui/i18n/_extract_en_keys.py",
}

WIDGET_NAMES = {
    "QLabel",
    "QPushButton",
    "QCheckBox",
    "QGroupBox",
    "QRadioButton",
    "QAction",
    "QToolButton",
    "QTabWidget",
}

UI_METHODS = {
    "setText",
    "setToolTip",
    "setPlaceholderText",
    "setWindowTitle",
    "setStatusTip",
    "setTabText",
    "setTitle",
    "setHorizontalHeaderLabels",
    "setHeaderLabels",
    "addTab",
    "setApplicationName",
    "set_brand",
    "set_stage",
}

MSG_BOX = {"warning", "information", "critical", "question"}

FILE_DIALOG = {"getOpenFileName", "getSaveFileName", "getExistingDirectory"}

TUPLE_ATTR_RE = re.compile(r"(LABELS|TITLES|OPTIONS|TIP|BLURBS?|ACTIONS|HEADERS)$", re.I)


def _func_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_ui_call(call: ast.Call) -> str | None:
    fn = _func_name(call.func)
    if fn in WIDGET_NAMES:
        return "widget"
    if fn in UI_METHODS:
        return "method"
    if fn in MSG_BOX and isinstance(call.func, ast.Attribute):
        if isinstance(call.func.value, ast.Name) and call.func.value.id == "QMessageBox":
            return "msgbox"
    if fn in FILE_DIALOG and isinstance(call.func, ast.Attribute):
        if isinstance(call.func.value, ast.Name) and call.func.value.id == "QFileDialog":
            return "filedialog"
    if fn == "attach_glass_tip":
        return "glass_tip"
    if fn == "setProperty":
        if call.args and isinstance(call.args[0], ast.Constant):
            if call.args[0].value == "glassTip":
                return "glass_tip"
    if fn == "addMenu" and isinstance(call.func, ast.Attribute):
        return "menu"
    return None


def _strings_from_node(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if node.value else []
    if isinstance(node, ast.JoinedStr):
        out: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value:
                out.append(v.value)
        return out
    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for elt in node.elts:
            out.extend(_strings_from_node(elt))
        return out
    return []


def should_skip_string(s: str, *, strict: bool) -> bool:
    if not s or s.isspace():
        return True
    if len(s) == 1 and s not in ("—", "…", "·", "▸", "▾", "←", "›"):
        return True
    if strict:
        # Stylesheet / objectName-ish
        if s.startswith("#") and re.match(r"^#[0-9A-Fa-f]{3,8}$", s):
            return True
        if re.match(r"^[a-z][a-zA-Z0-9]{2,}$", s) and " " not in s and "/" not in s:
            if s not in ("center", "near", "far", "auto", "max", "replace", "append"):
                return True
    if s in {"dark", "light", "Fusion", "replace", "append", "add", "remove"}:
        return True
    if re.match(r"^[a-z_]+\.[a-z_]+$", s) and " " not in s:
        return True
    return False


def collect_from_file(path: Path, keys: set[str]) -> None:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            fn = _func_name(node.func)
            if fn == "emit" and node.args:
                for s in _strings_from_node(node.args[0]):
                    if not should_skip_string(s, strict=False):
                        keys.add(s)
            for kw in node.keywords:
                if kw.arg in ("tip", "text", "title", "label", "caption"):
                    for s in _strings_from_node(kw.value):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
            kind = _is_ui_call(node)
            if kind == "widget" and node.args:
                for s in _strings_from_node(node.args[0]):
                    if not should_skip_string(s, strict=True):
                        keys.add(s)
            elif kind == "method":
                if node.args:
                    for s in _strings_from_node(node.args[0]):
                        if not should_skip_string(s, strict=True):
                            keys.add(s)
            elif kind == "msgbox":
                for arg in node.args[1:3]:
                    for s in _strings_from_node(arg):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
            elif kind == "filedialog":
                if len(node.args) >= 2:
                    for s in _strings_from_node(node.args[1]):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
                if len(node.args) >= 4:
                    for s in _strings_from_node(node.args[3]):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
            elif kind == "glass_tip":
                if len(node.args) >= 2:
                    for s in _strings_from_node(node.args[1]):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
            elif kind == "menu":
                if node.args:
                    for s in _strings_from_node(node.args[0]):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            for t in node.targets:
                if isinstance(t, ast.Name) and TUPLE_ATTR_RE.search(t.id):
                    for s in _strings_from_node(node.value):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
                if isinstance(t, ast.Attribute) and TUPLE_ATTR_RE.search(t.attr):
                    for s in _strings_from_node(node.value):
                        if not should_skip_string(s, strict=False):
                            keys.add(s)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name) and TUPLE_ATTR_RE.search(node.target.id):
                for s in _strings_from_node(node.value):
                    if not should_skip_string(s, strict=False):
                        keys.add(s)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        name = t.attr if isinstance(t, ast.Attribute) else (
                            t.id if isinstance(t, ast.Name) else None
                        )
                        if name and TUPLE_ATTR_RE.search(name):
                            for s in _strings_from_node(stmt.value):
                                if not should_skip_string(s, strict=False):
                                    keys.add(s)
            self.generic_visit(node)

    V().visit(tree)

    # Sidebar action tuples: ("Label", "action_id", bool)
    if "sidebar" in path.name:
        for m in re.finditer(r'\(\s*"([^"]+)"\s*,\s*"[^"]+"', src):
            s = m.group(1)
            if not should_skip_string(s, strict=False):
                keys.add(s)


def manual_additions(keys: set[str]) -> None:
    """F-string templates and dialog titles easy to miss in AST walks."""
    for s in (
        "Open {title}",
        "{n} KUID",
        "{n} KUIDs",
        "MSTN Trainz Studio — {out.stem}",
        "Fix uniform textures in-place for {len(paths)} file(s)?\n"
        "Writes sibling .bak once, then adds noise dots.",
        "ETA {m}:{s:02d}",
        "ETA {s}s",
        "{pct}%",
        "config.chump",
        "Pack chump",
        "Export config.txt",
        "Check texture.txt",
        "Scan folder for .texture.txt",
        "Load .lm.txt",
        "Light theme",
        "Dark theme",
        "MSTN Mesh Preview",
    ):
        keys.add(s)


def write_keys(keys: set[str], files_scanned: list[str]) -> int:
    manual_additions(keys)
    # Worker log prefixes (not shown as standalone UI copy)
    keys -= {"ve39_fix", "resize", "catalog"}

    sorted_keys = sorted(keys, key=lambda x: (x.lower(), x))

    lines = [
        '"""English UI string catalog (source = translation key). Auto-generated — re-run _run_extract.py."""',
        "",
        f"# Scanned {len(files_scanned)} files (ui/ except theme.py + io/ve39.py).",
        "",
        "KEYS = [",
    ]
    for k in sorted_keys:
        lines.append(f"    {k!r},")
    lines.append("]")
    lines.append("")
    OUT_KEYS.write_text("\n".join(lines), encoding="utf-8")
    return len(sorted_keys)


def write_glossary() -> None:
    content = '''"""VE / validation glossary — stable IDs for explanatory translations."""
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
        "Fix uniform textures in-place for the selected files? "
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
'''
    OUT_GLOSS.write_text(content, encoding="utf-8")


def main() -> None:
    files_scanned: list[str] = []
    keys: set[str] = set()

    for p in sorted(UI.rglob("*.py")):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        if rel in SKIP_FILES:
            continue
        files_scanned.append(rel)
        collect_from_file(p, keys)

    for p in IO_FILES:
        if p.is_file():
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            files_scanned.append(rel)
            collect_from_file(p, keys)
            # ve39 return messages shown in log UI
            for s in (
                "not found",
                "not uniform (skip)",
                "fixed (4×4)",
                "fixed (dots)",
            ):
                keys.add(s)

    count = write_keys(keys, files_scanned)
    write_glossary()
    print(f"Wrote {count} keys to {OUT_KEYS.name}")
    print(f"Scanned {len(files_scanned)} files")


if __name__ == "__main__":
    main()
