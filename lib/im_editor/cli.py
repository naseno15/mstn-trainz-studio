"""CLI front-end (also used by tools/im_att_edit.py shim)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import CAB_DEFAULT, ImDocument, parse_attachments, rebuild_im, selfcheck


def _parse_xyz(s: str) -> tuple[float, float, float]:
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise SystemExit(f"expected x,y,z got {s!r}")
    return float(parts[0]), float(parts[1]), float(parts[2])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Trainz .im attachment CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("im", type=Path, nargs="?", default=CAB_DEFAULT)
    p_list.add_argument("--grep", default=None)

    p_get = sub.add_parser("get")
    p_get.add_argument("im", type=Path, nargs="?", default=CAB_DEFAULT)
    p_get.add_argument("name")

    p_move = sub.add_parser("move")
    p_move.add_argument("im", type=Path, nargs="?", default=CAB_DEFAULT)
    p_move.add_argument("name")
    p_move.add_argument("--pos")
    p_move.add_argument("--dx", type=float, default=0.0)
    p_move.add_argument("--dy", type=float, default=0.0)
    p_move.add_argument("--dz", type=float, default=0.0)
    p_move.add_argument("--dry-run", action="store_true")

    p_ren = sub.add_parser("rename")
    p_ren.add_argument("im", type=Path, nargs="?", default=CAB_DEFAULT)
    p_ren.add_argument("old")
    p_ren.add_argument("new")
    p_ren.add_argument("--dry-run", action="store_true")

    sub.add_parser("selfcheck")

    args = ap.parse_args(argv)

    if args.cmd == "list":
        atts = parse_attachments(args.im.read_bytes())
        for a in atts:
            if args.grep and args.grep not in a.name:
                continue
            x, y, z = a.pos
            print(f"{a.name}\t{x:.6f}\t{y:.6f}\t{z:.6f}")
        return

    if args.cmd == "get":
        for a in parse_attachments(args.im.read_bytes()):
            if a.name == args.name:
                x, y, z = a.pos
                print(a.name)
                print(f"  pos    {x:.6f},{y:.6f},{z:.6f}")
                print(f"  orient {','.join(f'{v:.6f}' for v in a.orient)}")
                return
        raise SystemExit(f"attachment not found: {args.name}")

    if args.cmd == "move":
        doc = ImDocument()
        doc.open(args.im)
        hit = next((i for i, a in enumerate(doc.atts) if a.name == args.name), None)
        if hit is None:
            raise SystemExit(f"attachment not found: {args.name}")
        if args.pos:
            pos = _parse_xyz(args.pos)
        else:
            a = doc.atts[hit]
            pos = (a.pos[0] + args.dx, a.pos[1] + args.dy, a.pos[2] + args.dz)
        old = doc.atts[hit].pos
        print(f"{args.name}: {old} -> {pos}")
        if args.dry_run:
            return
        doc.update_one(hit, pos=pos)
        doc.save()
        return

    if args.cmd == "rename":
        doc = ImDocument()
        doc.open(args.im)
        hit = next((i for i, a in enumerate(doc.atts) if a.name == args.old), None)
        if hit is None:
            raise SystemExit(f"attachment not found: {args.old}")
        if any(a.name == args.new for a in doc.atts):
            raise SystemExit(f"name already exists: {args.new}")
        print(f"rename {args.old} -> {args.new}")
        if args.dry_run:
            rebuild_im(doc.base, doc.atts)
            return
        doc.update_one(hit, name=args.new)
        doc.save()
        return

    if args.cmd == "selfcheck":
        print(selfcheck())
        return

    ap.error("unknown command")


if __name__ == "__main__":
    main(sys.argv[1:])
