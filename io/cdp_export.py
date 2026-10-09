"""Export installed assets with TrainzUtil createCDP.

One CDP per KUID, or one CDP that holds every selected KUID.
The launcher must be open; this does not pack loose folders.
"""
from __future__ import annotations

import re
from pathlib import Path

from .trainz_install import run_trainzutil

_SAFE = re.compile(r"[^A-Za-z0-9]+")


def cdp_filename(kuid: str) -> str:
    token = (kuid or "").strip().strip("<>")
    safe = _SAFE.sub("_", token).strip("_")
    return f"{safe or 'asset'}.cdp"


def createcdp_args(dest: Path, kuids: list[str]) -> list[str]:
    return ["createCDP", str(dest), *kuids]


def export_succeeded(text: str, dest: Path) -> bool:
    if not dest.is_file() or dest.stat().st_size < 8:
        return False
    return "0 Errors" in (text or "")


def export_cdp(exe: Path, dest: Path, kuids: list[str], *, timeout: float = 600) -> str:
    """Run createCDP. Replaces dest when it already exists."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    return run_trainzutil(exe, createcdp_args(dest, kuids), timeout=timeout)


def _self_check() -> None:
    assert cdp_filename("<kuid:1125787:100058>") == "kuid_1125787_100058.cdp"
    assert cdp_filename("<kuid2:1:2:3>") == "kuid2_1_2_3.cdp"
    args = createcdp_args(Path("out.cdp"), ["<kuid:1:2>", "<kuid:3:4>"])
    assert args == ["createCDP", "out.cdp", "<kuid:1:2>", "<kuid:3:4>"]
    missing = Path("_no_such_cdp_.cdp")
    assert export_succeeded("OK (0 Errors, 0 Warnings)", missing) is False
