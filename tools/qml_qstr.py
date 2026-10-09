"""Wrap visible QML strings in qsTr() so UiLang (CatalogTranslator) can translate them.

Rewrites `text:` / `label:` / `tip:` / `tipText:` / `title:` / `placeholderText:` bindings:
  - string literals → qsTr("…")
  - a bare property chain (bridge.foo, modelData, label) → qsTr(chain); misses fall back to the source text.
Skips editable text items (TextEdit/TextInput/TextField/TextArea), colors, and lines already using qsTr.
Idempotent — re-run after adding QML.  Usage: python tools/qml_qstr.py [--check]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

QML = Path(__file__).resolve().parents[1] / "ui" / "qml"
PROPS = ("text", "label", "tip", "tipText", "title", "placeholderText")
BIND = re.compile(r"^(\s*)(" + "|".join(PROPS) + r")(\s*:\s*)(.+?)\s*$")
ELEMENT = re.compile(r"^\s*(?:[\w.]+\s*:\s*)?([A-Z]\w*)\s*\{")
EDITABLE = {"TextEdit", "TextInput", "TextField", "TextArea"}
LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')
CHAIN = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
CONTINUES_AFTER = ("?", ":", "+", "(", "||", "&&", ",")
CONTINUES_BEFORE = ("?", ":", "+", "||", "&&", ")")


BOUNDARY = re.compile(r"[?:,]|\|\||&&")


def is_logic_literal(rhs: str, start: int, end: int) -> bool:
    """Literal used as a key (compared, or passed to a call) — translating it would break logic."""
    before = BOUNDARY.split(rhs[:start])[-1]
    after = BOUNDARY.split(rhs[end:])[0]
    if "==" in before or "!=" in before or "==" in after or "!=" in after:
        return True
    return re.search(r"[\w\]]\s*\(\s*$", rhs[:start]) is not None


def wrap_literals(rhs: str) -> str:
    def repl(m: re.Match) -> str:
        body = m.group(0)[1:-1]
        if rhs[max(0, m.start() - 5):m.start()] == "qsTr(" or is_logic_literal(rhs, m.start(), m.end()):
            return m.group(0)
        if not re.search(r"[A-Za-z\u0080-\uffff]", body) or body.startswith("#") or re.fullmatch(r"[\w./-]+\.(png|svg|qml|jpg)", body):
            return m.group(0)
        return f"qsTr({m.group(0)})"

    return LITERAL.sub(repl, rhs)


def wrap_chain(code: str) -> str:
    # qsTr() throws on non-strings (counts, undefined) — only route strings through it.
    return f'(typeof {code} === "string" ? qsTr({code}) : {code})'


def transform(text: str) -> str:
    out: list[str] = []
    stack: list[str] = []
    cont = False
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        new = line
        editable = bool(stack) and stack[-1] in EDITABLE
        if cont and not editable and "qsTr" not in line:
            new = wrap_literals(line)
        m = BIND.match(line)
        cont = False
        if m and not editable and "qsTr" not in line and not stripped.startswith("property"):
            indent, name, colon, rhs = m.groups()
            code = rhs.split("//")[0].rstrip() if '"' not in rhs else rhs
            if CHAIN.match(code) and code not in ("true", "false", "null", "undefined"):
                new = f"{indent}{name}{colon}{wrap_chain(code)}"
            else:
                new = f"{indent}{name}{colon}{wrap_literals(rhs)}"
            cont = code.endswith(CONTINUES_AFTER)
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if (m or cont) and nxt.startswith(CONTINUES_BEFORE):
            cont = True
        out.append(new)
        em = ELEMENT.match(line)
        if em:
            stack.append(em.group(1))
        opens = line.count("{") - (1 if em else 0)
        closes = line.count("}")
        stack.extend(["{"] * max(0, opens))
        for _ in range(closes):
            if stack:
                stack.pop()
    return "\n".join(out)


def main() -> int:
    check = "--check" in sys.argv
    changed = 0
    for path in sorted(QML.glob("*.qml")):
        src = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in src else "\n"
        dst = transform(src.replace("\r\n", "\n")).replace("\n", eol)
        if dst != src:
            changed += 1
            if not check:
                path.write_text(dst, encoding="utf-8", newline="")
            print(("would change " if check else "wrapped ") + path.name)
    assert transform('Text {\n    text: "Open"\n}') == 'Text {\n    text: qsTr("Open")\n}'
    assert transform('TextEdit {\n    text: bridge.body\n}') == 'TextEdit {\n    text: bridge.body\n}'
    assert transform('Text { color: "#fff" }') == 'Text { color: "#fff" }'
    assert transform("Text {\n    text: bridge.label\n}") == 'Text {\n    text: (typeof bridge.label === "string" ? qsTr(bridge.label) : bridge.label)\n}'
    assert transform(transform('Text {\n    text: a ? "A" : "B"\n}')) == 'Text {\n    text: a ? qsTr("A") : qsTr("B")\n}'
    assert transform('Text {\n    text: bridge.page === "meshops" ? "Drop mesh" : "Drop images"\n}') == 'Text {\n    text: bridge.page === "meshops" ? qsTr("Drop mesh") : qsTr("Drop images")\n}'
    assert transform('Btn {\n    tip: side.tip("redo")\n}') == 'Btn {\n    tip: side.tip("redo")\n}'
    assert transform('Text {\n    text: n + " errors"\n}') == 'Text {\n    text: n + qsTr(" errors")\n}'
    return 1 if check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
