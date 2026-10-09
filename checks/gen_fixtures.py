"""Write phase-1 golden files from the Python readers. Run from anywhere."""
from __future__ import annotations

import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from trainz_studio.io import chump, cdp, im_geom, tzarc
from trainz_studio.io.chump import (
    TYPE_INT,
    TYPE_KUID,
    TYPE_SOUP,
    TYPE_TEXT,
    ChumpSoup,
    ChumpTag,
)
from trainz_studio.lib.trainzmesh_viewer.parser import parse_trainzmesh

OUT = Path(__file__).resolve().parent / "fixtures"


def fmt_f(value: float) -> str:
    nearest = round(value)
    if abs(value - nearest) < 1e-5:
        return str(int(nearest))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def summarize_chump(node: chump.ChumpFile) -> str:
    lines: list[str] = []

    def walk(tags: list, indent: str) -> None:
        for tag in tags:
            if tag.type == TYPE_SOUP:
                lines.append(f"{indent}soup {tag.name}")
                assert isinstance(tag.value, ChumpSoup)
                walk(tag.value.children, indent + "  ")
            elif tag.type == TYPE_TEXT:
                lines.append(f"{indent}text {tag.name}={tag.value}")
            elif tag.type == TYPE_INT:
                lines.append(
                    f"{indent}int {tag.name}=" + ",".join(str(int(v)) for v in tag.value)
                )
            elif tag.type == TYPE_KUID:
                from trainz_studio.io import kuid_bin

                lines.append(
                    f"{indent}kuid {tag.name}={kuid_bin.bytes_to_kuid(bytes(tag.value))}"
                )

    walk(node.root, "")
    return "\n".join(lines) + "\n"


def write_chump() -> None:
    from trainz_studio.io import kuid_bin

    node = chump.ChumpFile(
        root=[
            ChumpTag.text("username", "Demo"),
            ChumpTag.integer("count", 2, 3),
            ChumpTag.kuid("kuid", kuid_bin.parse_kuid_string("<kuid2:1190880:100078:1>")),
            ChumpTag.soup("mesh", [ChumpTag.text("name", "body")]),
        ]
    )
    blob = chump.encode_chump(node)
    (OUT / "chump.bin").write_bytes(blob)
    again = chump.read_chump(blob)
    (OUT / "chump.txt").write_text(summarize_chump(again), encoding="utf-8")


def write_cdp() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "asset"
        folder.mkdir()
        (folder / "config.txt").write_text(
            'username  "Demo"\nkind  "scenery"\nkuid  <kuid:1:2>\n',
            encoding="utf-8",
        )
        (folder / "note.txt").write_text("hello cdp", encoding="utf-8")
        dest = OUT / "demo.cdp"
        cdp.pack_asset_folders([folder], dest, package_name="phase1")
    loaded = cdp.load_cdp(OUT / "demo.cdp")
    kuids = cdp.list_cdp_kuids(OUT / "demo.cdp")
    note = cdp.read_file_bytes(loaded, kuids[0], "note.txt")
    (OUT / "cdp.txt").write_text(
        f"kuid {kuids[0]}\nfile note.txt {note.decode('utf-8')}\n",
        encoding="utf-8",
    )


def _tzarc_v1(name: str, payload: bytes) -> bytes:
    directory = bytearray()
    directory += struct.pack(">I", 1)
    directory.append(len(name))
    directory += name.encode("ascii")
    directory += struct.pack(">Q", len(payload))
    directory += b"\x00\x00\x00\x00"
    directory += payload
    return b"TZac" + struct.pack(">I", 1) + bytes(directory)


def _tzarc_v2(inner: bytes) -> bytes:
    comp = zlib.compress(inner)
    out = bytearray()
    out += b"TZac"
    out += struct.pack(">I", 2)
    out += struct.pack("<Q", len(inner))
    out += struct.pack("<I", 1)
    out += struct.pack("<H", len(comp) - 1)
    out += comp
    return bytes(out)


def write_tzarc() -> None:
    v1 = _tzarc_v1("config.txt", b"hello-v1")
    (OUT / "sample.tzarc").write_bytes(v1)
    inner = bytearray()
    inner += struct.pack(">I", 1)
    inner.append(len("config.txt"))
    inner += b"config.txt"
    inner += struct.pack(">Q", len(b"hello-v2"))
    inner += b"\x11\x22\x33\x44"
    inner += b"hello-v2"
    v2 = _tzarc_v2(bytes(inner))
    (OUT / "sample2.tzarc").write_bytes(v2)
    a = tzarc.read_tzarc_config(OUT / "sample.tzarc")
    b = tzarc.read_tzarc_config(OUT / "sample2.tzarc")
    (OUT / "tzarc.txt").write_text(
        f"v1 config.txt {a.decode('ascii')}\nv2 config.txt {b.decode('ascii')}\n",
        encoding="utf-8",
    )


def _jet(name: str) -> bytes:
    raw = name.encode("utf-8") + b"\x00"
    pad = (4 - len(raw) % 4) % 4
    body = raw + (b"\x00" * pad)
    return struct.pack("<I", len(body)) + body


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + struct.pack("<I", len(body)) + body


def write_im() -> None:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    normals = struct.pack("<9f", 0, 0, 1, 0, 0, 1, 0, 0, 1)
    geom = bytearray()
    geom += struct.pack("<I", 101)
    geom += struct.pack("<I", 4)
    geom += struct.pack("<f", 0.5)
    geom += struct.pack("<I", 3)
    geom += struct.pack("<I", 1)
    geom += struct.pack("<I", 3)
    geom += struct.pack("<I", 0)
    geom += positions
    geom += indices
    geom += normals
    matl = struct.pack("<I", 102) + _jet("body")
    nested = _chunk(b"MATL", matl) + _chunk(b"GEOM", bytes(geom))
    chnk = _chunk(b"CHNK", b"\x00" * 8 + nested)
    body = b"IDXM" + chnk
    data = b"JIRF" + struct.pack("<I", len(body)) + body
    parts = im_geom.parse_im_parts(data)
    (OUT / "tri.im").write_bytes(data)
    part = parts[0]
    lines = [
        f"parts {len(parts)}",
        f"name {part.name}",
        f"verts {len(part.vertices)}",
        "idx " + ",".join(str(int(i)) for i in part.indices),
    ]
    for i, row in enumerate(part.vertices):
        lines.append(
            f"pos{i} " + ",".join(fmt_f(float(c)) for c in row)
        )
    (OUT / "im.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_tzmf() -> None:
    fmt = b"S0_P3fN3fT02f"
    positions = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0),
    ]
    verts = b"".join(struct.pack("<8f", *row) for row in positions)
    indices = struct.pack("<3H", 0, 1, 2)

    def le_str(text: str) -> bytes:
        raw = text.encode("ascii")
        return struct.pack("<I", len(raw)) + raw

    tail = le_str("m.pbrmetal") + le_str("txalbedo") + le_str("body.texture")
    counts = struct.pack(">III", 3, 3, 32)
    payload = fmt + b"\x00" + counts + verts + indices + tail
    data = b"tzMF" + struct.pack(">IIII", 1, 0, 0, 1) + payload
    mesh = parse_trainzmesh("tri.trainzmesh", data)
    (OUT / "tri.trainzmesh").write_bytes(data)
    sub = mesh.submeshes[0]
    lines = [
        f"version {mesh.version}",
        f"count {len(mesh.submeshes)}",
        f"name {sub.name}",
        f"verts {len(sub.positions)}",
        "idx " + ",".join(str(int(i)) for i in sub.indices),
    ]
    for i, row in enumerate(sub.positions):
        lines.append(f"pos{i} " + ",".join(fmt_f(float(c)) for c in row))
    for i, row in enumerate(sub.uvs):
        lines.append(f"uv{i} " + ",".join(fmt_f(float(c)) for c in row))
    lines.append(f"albedo {sub.albedo}")
    lines.append(f"mat {sub.material_type}")
    (OUT / "tzmf.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_chump()
    write_cdp()
    write_tzarc()
    write_im()
    write_tzmf()
    print("fixtures ok", OUT)


if __name__ == "__main__":
    main()
