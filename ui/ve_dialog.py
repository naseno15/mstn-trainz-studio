"""App-wide VE Rules report dialog — shared by Mesh / Assets / Engine / Sounds."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..io.ve_rules import VeReport, format_report, summarize_reports


def reports_to_text(reports: list[VeReport]) -> str:
    body = "\n\n".join(format_report(r) for r in reports if r.findings)
    return body or "(no VE issues)"


def show_ve_reports(
    parent: QWidget | None,
    reports: list[VeReport],
    *,
    title: str = "VE Rules",
    folder: Path | None = None,
) -> None:
    """Modal report for any studio."""
    summary = summarize_reports(reports)
    head = summary["line"]
    if folder is not None:
        head = f"{folder} — {head}"
    body = reports_to_text(reports)

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(760, 540)
    lay = QVBoxLayout(dlg)
    tip = QLabel(head)
    tip.setObjectName("mutedTip")
    tip.setWordWrap(True)
    lay.addWidget(tip)
    view = QTextEdit()
    view.setReadOnly(True)
    view.setPlainText(body)
    lay.addWidget(view, 1)
    row = QHBoxLayout()
    row.addStretch(1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dlg.reject)
    buttons.accepted.connect(dlg.accept)
    row.addWidget(buttons)
    lay.addLayout(row)
    dlg.exec()
