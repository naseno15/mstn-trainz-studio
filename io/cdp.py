"""Trainz *.cdp pack / extract / browse — CDPExplorer chump-format (MIT notes).

List assets, pack asset folders (LZSS level-0 store), extract folders,
browse/edit the tag tree. BINARY decompress via ``cdp_lzss`` (cdptool port).
"""
from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import kuid_bin
from .cdp_lzss import decode_binary_blob, make_binary_blob
from .chump import (
    TYPE_KUID,
    TYPE_RAW,
    TYPE_SOUP,
    TYPE_TEXT,
    ChumpFile,
    ChumpSoup,
    ChumpTag,
    chump_to_text,
    read_chump,
    text_to_chump,
    write_chump,
)

MAGIC = b"ACS$"

# Soft guidance + hard ceiling for packed CDP size (bytes).
SIZE_OK_MAX = 500 * 1024 * 1024
SIZE_SOFT_MAX = 800 * 1024 * 1024
SIZE_HARD_MAX = 1024 * 1024 * 1024

_SKIP_NAMES = {
    "thumbs.db",
    "desktop.ini",
    ".ds_store",
    "config.chump",
}
_SKIP_SUFFIXES = {".bak", ".tmp", ".temp"}


@dataclass
class CdpAsset:
    kuid: str = ""
    username: str = ""
    kind: str = ""
    trainz_build: str = ""
    category_class: str = ""
    category_region: str = ""
    category_era: str = ""
    description: str = ""


@dataclass
class CdpIndex:
    path: Path
    assets: list[CdpAsset] = field(default_factory=list)


@dataclass
class CdpFileNode:
    """One file (or nested CDP) inside an asset's ``files`` tree."""

    rel_path: str
    size: int  # uncompressed when known; -1 if decode fails
    is_cdp: bool = False
    blob: bytes = b""  # raw BINARY payload (size prefix + lzss)


@dataclass
class CdpAssetNode:
    kuid: str
    username: str
    kind: str
    files: list[CdpFileNode] = field(default_factory=list)


@dataclass
class SizeVerdict:
    total: int
    band: str  # ok | soft | warn | refuse
    label: str


def classify_size(total: int) -> SizeVerdict:
    if total > SIZE_HARD_MAX:
        return SizeVerdict(total, "refuse", "เกิน 1 GB — ห้าม pack")
    if total > SIZE_SOFT_MAX:
        return SizeVerdict(total, "warn", "เกินพอดี (≤800 MB แนะนำ) — ยัง pack ได้")
    if total > SIZE_OK_MAX:
        return SizeVerdict(total, "soft", "พอดีแต่เกินพอดี (≤500 MB แนะนำ)")
    return SizeVerdict(total, "ok", "พอดีจริง (≤500 MB)")


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


# ── open / list (legacy scraper kept for KUID copy) ─────────────────────────


class _AssetDraft:
    def __init__(self) -> None:
        self.kuid = ""
        self.username = "Untitled"
        self.kind = ""
        self.trainz_build = ""
        self.category_class = ""
        self.category_region = ""
        self.category_era = ""
        self.description = ""
        self._kuid_bytes: bytes | None = None

    def finish(self) -> CdpAsset:
        kuid = self.kuid
        if not kuid and self._kuid_bytes is not None:
            kuid = kuid_bin.bytes_to_kuid(self._kuid_bytes)
        return CdpAsset(
            kuid=kuid,
            username=self.username,
            kind=self.kind,
            trainz_build=self.trainz_build,
            category_class=self.category_class,
            category_region=self.category_region,
            category_era=self.category_era,
            description=self.description,
        )


def open_cdp(path: Path) -> CdpIndex:
    path = Path(path)
    data = memoryview(path.read_bytes())
    if len(data) < 16 or bytes(data[:4]) != MAGIC:
        raise ValueError(f"not a CDP/chump: {path.name}")
    chump_len = struct.unpack_from("<I", data, 12)[0]
    start = 16
    end = min(start + chump_len, len(data))
    assets: list[CdpAsset] = []
    pos = start
    while pos < end:
        pos = _parse_tag(data, pos, end, parent="", assets=assets, draft=None)
    return CdpIndex(path=path, assets=assets)


def list_cdp_kuids(path: Path) -> list[str]:
    return [a.kuid for a in open_cdp(path).assets if a.kuid]


def load_cdp(path: Path | bytes) -> ChumpFile:
    return read_chump(path)


def cdp_bak_path(path: Path) -> Path:
    """Sibling temp backup: ``foo.cdp`` → ``foo.cdp.bak``."""
    path = Path(path)
    return path.with_suffix(path.suffix + ".bak")


def discard_cdp_bak(path: Path | None) -> bool:
    """Remove sibling ``*.cdp.bak`` if present. Returns True when removed."""
    if path is None:
        return False
    bak = cdp_bak_path(Path(path))
    if not bak.is_file():
        return False
    try:
        bak.unlink()
    except OSError:
        return False
    return True


def save_cdp(path: Path, chump: ChumpFile, *, bak: bool = True) -> Path:
    """Write CDP; temp sibling ``*.cdp.bak`` during overwrite, removed on success.

    On write failure the ``.bak`` is left for recovery. Callers may also
    ``discard_cdp_bak`` on Clear / abandon.
    """
    path = Path(path)
    wrote_bak = False
    if bak and path.is_file():
        bak_path = cdp_bak_path(path)
        bak_path.write_bytes(path.read_bytes())
        wrote_bak = True
    try:
        write_chump(path, chump)
    except Exception:
        raise
    if wrote_bak:
        discard_cdp_bak(path)
    return path


# ── browse tree ─────────────────────────────────────────────────────────────


def browse_cdp(chump: ChumpFile) -> list[CdpAssetNode]:
    assets_tag = _find_child(chump.root, "assets")
    if assets_tag is None or assets_tag.type != TYPE_SOUP:
        return []
    assert isinstance(assets_tag.value, ChumpSoup)
    out: list[CdpAssetNode] = []
    for asset in assets_tag.value.children:
        if asset.type != TYPE_SOUP:
            continue
        assert isinstance(asset.value, ChumpSoup)
        kuid = asset.name
        username = _text_child(asset.value.children, "username") or "Untitled"
        kind = _text_child(asset.value.children, "kind") or ""
        files_tag = _find_child(asset.value.children, "files")
        files: list[CdpFileNode] = []
        if files_tag is not None and files_tag.type == TYPE_SOUP:
            assert isinstance(files_tag.value, ChumpSoup)
            _collect_files(files_tag.value.children, "", files)
        out.append(CdpAssetNode(kuid=kuid, username=username, kind=kind, files=files))
    return out


def _collect_files(tags: list[ChumpTag], prefix: str, out: list[CdpFileNode]) -> None:
    for tag in tags:
        if tag.type == TYPE_SOUP:
            assert isinstance(tag.value, ChumpSoup)
            _collect_files(tag.value.children, f"{prefix}{tag.name}/", out)
            continue
        if tag.type != TYPE_RAW and tag.type != 4:
            continue
        blob = bytes(tag.value) if isinstance(tag.value, (bytes, bytearray)) else b""
        size = -1
        is_cdp = tag.name.lower().endswith(".cdp")
        if len(blob) >= 4:
            size = struct.unpack_from("<I", blob, 0)[0]
            if is_cdp:
                try:
                    data = decode_binary_blob(blob)
                    is_cdp = len(data) >= 4 and data[:4] == MAGIC
                except Exception:
                    pass
        out.append(
            CdpFileNode(
                rel_path=f"{prefix}{tag.name}",
                size=size,
                is_cdp=is_cdp,
                blob=blob,
            )
        )


def read_file_bytes(chump: ChumpFile, asset_kuid: str, rel_path: str) -> bytes:
    tag = _file_tag(chump, asset_kuid, rel_path)
    if tag is None:
        raise KeyError(f"missing {asset_kuid}/{rel_path}")
    blob = bytes(tag.value) if isinstance(tag.value, (bytes, bytearray)) else b""
    return decode_binary_blob(blob)


_MESH_PREVIEW_EXTS = {
    ".trainzmesh",
    ".fbx",
    ".im",
    ".pm",
    ".tga",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".dds",
    ".webp",
    ".gif",
}
_MESH_PREVIEW_NAMES = {"mesh.txt"}


def is_mesh_preview_name(name: str) -> bool:
    n = name.lower().replace("\\", "/")
    base = Path(n).name
    if base in _MESH_PREVIEW_NAMES:
        return True
    if base.endswith(".texture.txt") or base.endswith(".texture"):
        return True
    return Path(base).suffix in _MESH_PREVIEW_EXTS


def safe_stage_token(kuid: str) -> str:
    raw = re.sub(r"[^\w.-]+", "_", kuid.strip())[:80]
    digest = hashlib.sha1(kuid.encode("utf-8")).hexdigest()[:10]
    return f"{raw}_{digest}" if raw else digest


def stage_asset_for_mesh_preview(
    chump: ChumpFile,
    asset_kuid: str,
    dest: Path,
    *,
    mesh_rel: str | None = None,
    mesh_only: bool = False,
) -> Path:
    """Extract mesh + texture sidecars from one CDP asset into ``dest``.

    Skips audio / nested CDP / junk so preview stays fast. Returns path to
    ``mesh_rel`` under ``dest`` (or ``dest`` if mesh_rel omitted).

    ``mesh_only=True`` writes just the mesh file (fast first paint); call again
    with ``mesh_only=False`` to fill texture sidecars.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    assets = browse_cdp(chump)
    asset = next((a for a in assets if a.kuid == asset_kuid), None)
    if asset is None:
        raise KeyError(f"missing asset {asset_kuid}")
    mesh_norm = (mesh_rel or "").replace("\\", "/")
    for fn in asset.files:
        rel = str(fn.rel_path).replace("\\", "/")
        if mesh_only:
            if not mesh_norm or rel != mesh_norm:
                continue
        else:
            keep = is_mesh_preview_name(rel)
            if mesh_norm and rel == mesh_norm:
                keep = True
            if not keep:
                continue
        data = read_file_bytes(chump, asset_kuid, rel)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    if mesh_norm:
        mesh_path = dest / mesh_norm
        if not mesh_path.is_file():
            raise FileNotFoundError(f"staged mesh missing: {mesh_norm}")
        return mesh_path
    return dest


def asset_config_text(chump: ChumpFile, asset_kuid: str) -> str:
    """config.txt-like text for one asset (without files / compression)."""
    tag = _asset_tag(chump, asset_kuid)
    if tag is None or tag.type != TYPE_SOUP:
        raise KeyError(f"missing asset {asset_kuid}")
    assert isinstance(tag.value, ChumpSoup)
    return chump_to_text(_asset_config_chump(tag.value.children))


def replace_asset_config(chump: ChumpFile, asset_kuid: str, text: str) -> None:
    """Replace asset config tags from config.txt text; keep files / compression / dsid."""
    tag = _asset_tag(chump, asset_kuid)
    if tag is None or tag.type != TYPE_SOUP:
        raise KeyError(f"missing asset {asset_kuid}")
    assert isinstance(tag.value, ChumpSoup)
    kept = [
        t
        for t in tag.value.children
        if t.name in ("files", "compression", "dsid")
    ]
    fresh = text_to_chump(text)
    new_children = [
        t
        for t in fresh.root
        if t.name not in ("files", "compression", "dsid")
    ]
    tag.value.children = new_children + kept


def remove_asset(chump: ChumpFile, asset_kuid: str) -> bool:
    assets_tag = _find_child(chump.root, "assets")
    if assets_tag is None or assets_tag.type != TYPE_SOUP:
        return False
    assert isinstance(assets_tag.value, ChumpSoup)
    before = len(assets_tag.value.children)
    assets_tag.value.children = [
        c for c in assets_tag.value.children if not (c.type == TYPE_SOUP and c.name == asset_kuid)
    ]
    if len(assets_tag.value.children) == before:
        return False
    _rebuild_contents_table(chump)
    return True


def remove_file(chump: ChumpFile, asset_kuid: str, rel_path: str) -> bool:
    parent, name = _file_parent(chump, asset_kuid, rel_path)
    if parent is None:
        return False
    before = len(parent.children)
    parent.children = [c for c in parent.children if c.name != name]
    return len(parent.children) != before


def replace_file(chump: ChumpFile, asset_kuid: str, rel_path: str, data: bytes) -> None:
    tag = _file_tag(chump, asset_kuid, rel_path)
    if tag is None:
        raise KeyError(f"missing {asset_kuid}/{rel_path}")
    tag.type = TYPE_RAW
    tag.value = make_binary_blob(data)


# ── extract / pack ──────────────────────────────────────────────────────────


def extract_cdp(path: Path, dest: Path) -> list[Path]:
    """Extract each asset to ``dest/<safe_kuid>/`` with config.txt + files."""
    path = Path(path)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    chump = load_cdp(path)
    written: list[Path] = []
    for asset in browse_cdp(chump):
        folder = dest / _safe_name(asset.kuid or asset.username or "asset")
        folder.mkdir(parents=True, exist_ok=True)
        asset_tag = _asset_tag(chump, asset.kuid)
        if asset_tag is None:
            continue
        assert isinstance(asset_tag.value, ChumpSoup)
        cfg = _asset_config_chump(asset_tag.value.children)
        cfg_path = folder / "config.txt"
        cfg_path.write_text(chump_to_text(cfg), encoding="utf-8")
        written.append(cfg_path)
        for fn in asset.files:
            data = decode_binary_blob(fn.blob)
            out = folder / fn.rel_path
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            written.append(out)
    return written


def estimate_pack_size(folders: list[Path]) -> int:
    total = 256  # archive wrapper overhead (rough)
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for f in _iter_asset_files(folder):
            total += f.stat().st_size + 64
        cfg = folder / "config.txt"
        if cfg.is_file():
            total += cfg.stat().st_size + 128
    return total


def pack_asset_folders(
    folders: list[Path],
    dest: Path,
    *,
    package_name: str = "unknown",
) -> tuple[Path, SizeVerdict]:
    """Pack asset folders (each with config.txt) into one CDP.

    Files stored as LZSS level-0 (valid BINARY wire). Raises if > 1 GB.
    """
    folders = [Path(f) for f in folders if Path(f).is_dir()]
    if not folders:
        raise ValueError("no asset folders to pack")
    est = estimate_pack_size(folders)
    verdict = classify_size(est)
    if verdict.band == "refuse":
        raise ValueError(f"{verdict.label} ({format_bytes(est)})")

    asset_tags: list[ChumpTag] = []
    kuids: list[bytes] = []
    for folder in folders:
        tag, raw_kuid = _pack_one_folder(folder)
        asset_tags.append(tag)
        kuids.append(raw_kuid)

    contents_children = [
        ChumpTag.kuid(str(i), raw) for i, raw in enumerate(kuids)
    ]
    root = [
        ChumpTag.soup("assets", asset_tags),
        ChumpTag.soup("contents-table", contents_children),
        ChumpTag.soup("kuid-table", []),
        ChumpTag.soup("obsolete-table", []),
        ChumpTag.text("kind", "archive"),
        ChumpTag.integer("package-version", 1),
        ChumpTag.text("username", package_name or "unknown"),
    ]
    dest = Path(dest)
    if dest.suffix.lower() != ".cdp":
        dest = dest.with_suffix(".cdp")
    save_cdp(dest, ChumpFile(root=root))
    actual = dest.stat().st_size
    return dest, classify_size(actual)


def _pack_one_folder(folder: Path) -> tuple[ChumpTag, bytes]:
    cfg_path = folder / "config.txt"
    if not cfg_path.is_file():
        raise ValueError(f"missing config.txt in {folder}")
    text = cfg_path.read_text(encoding="utf-8", errors="replace")
    cfg = text_to_chump(text)
    children = [
        t
        for t in cfg.root
        if not (t.name in ("files", "compression", "dsid") or t.name.startswith("files"))
    ]
    raw_kuid = _kuid_from_tags(children)
    if raw_kuid is None:
        raise ValueError(f"no kuid in {cfg_path}")
    kuid_str = kuid_bin.bytes_to_kuid(raw_kuid)

    file_tags = _build_files_tree(folder)
    children.append(ChumpTag.text("compression", "LZSS"))
    children.append(ChumpTag.soup("files", file_tags))
    return ChumpTag.soup(kuid_str, children), raw_kuid


def _build_files_tree(folder: Path) -> list[ChumpTag]:
    """Build nested ``files`` container from folder contents (skip config.txt)."""
    root_soup: list[ChumpTag] = []
    # path parts → soup children list
    containers: dict[tuple[str, ...], list[ChumpTag]] = {(): root_soup}

    for path in _iter_asset_files(folder):
        rel = path.relative_to(folder)
        parts = rel.parts
        if not parts:
            continue
        # ensure parent containers
        for i in range(len(parts) - 1):
            key = parts[: i + 1]
            parent_key = parts[:i]
            if key not in containers:
                soup = ChumpSoup([])
                containers[parent_key].append(ChumpTag(parts[i], TYPE_SOUP, soup))
                containers[key] = soup.children
        data = path.read_bytes()
        containers[parts[:-1]].append(
            ChumpTag(parts[-1], TYPE_RAW, make_binary_blob(data))
        )
    return root_soup


def _iter_asset_files(folder: Path):
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        name = p.name.lower()
        if name == "config.txt":
            continue
        if name in _SKIP_NAMES:
            continue
        if p.suffix.lower() in _SKIP_SUFFIXES:
            continue
        # skip hidden
        if any(part.startswith(".") for part in p.relative_to(folder).parts):
            continue
        yield p


# ── helpers ─────────────────────────────────────────────────────────────────


def _safe_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in name.strip())
    return out or "asset"


def _find_child(tags: list[ChumpTag], name: str) -> ChumpTag | None:
    for t in tags:
        if t.name == name:
            return t
    return None


def _text_child(tags: list[ChumpTag], name: str) -> str:
    t = _find_child(tags, name)
    if t is None or t.type != TYPE_TEXT:
        return ""
    return str(t.value or "")


def _asset_tag(chump: ChumpFile, kuid: str) -> ChumpTag | None:
    assets = _find_child(chump.root, "assets")
    if assets is None or assets.type != TYPE_SOUP:
        return None
    assert isinstance(assets.value, ChumpSoup)
    return _find_child(assets.value.children, kuid)


def _asset_config_chump(children: list[ChumpTag]) -> ChumpFile:
    kept = [
        t
        for t in children
        if t.name not in ("files", "compression", "dsid")
    ]
    return ChumpFile(root=kept)


def _kuid_from_tags(tags: list[ChumpTag]) -> bytes | None:
    t = _find_child(tags, "kuid")
    if t is None:
        return None
    if t.type == TYPE_KUID and isinstance(t.value, (bytes, bytearray)):
        return bytes(t.value[:8])
    if t.type == TYPE_TEXT and isinstance(t.value, str):
        return kuid_bin.parse_kuid_string(t.value)
    return None


def _file_tag(chump: ChumpFile, asset_kuid: str, rel_path: str) -> ChumpTag | None:
    parent, name = _file_parent(chump, asset_kuid, rel_path)
    if parent is None:
        return None
    return _find_child(parent.children, name)


def _file_parent(
    chump: ChumpFile, asset_kuid: str, rel_path: str
) -> tuple[ChumpSoup | None, str]:
    asset = _asset_tag(chump, asset_kuid)
    if asset is None or asset.type != TYPE_SOUP:
        return None, ""
    assert isinstance(asset.value, ChumpSoup)
    files = _find_child(asset.value.children, "files")
    if files is None or files.type != TYPE_SOUP:
        return None, ""
    assert isinstance(files.value, ChumpSoup)
    parts = Path(rel_path.replace("\\", "/")).parts
    if not parts:
        return None, ""
    cur = files.value
    for part in parts[:-1]:
        child = _find_child(cur.children, part)
        if child is None or child.type != TYPE_SOUP:
            return None, ""
        assert isinstance(child.value, ChumpSoup)
        cur = child.value
    return cur, parts[-1]


def _rebuild_contents_table(chump: ChumpFile) -> None:
    assets = _find_child(chump.root, "assets")
    if assets is None or assets.type != TYPE_SOUP:
        return
    assert isinstance(assets.value, ChumpSoup)
    children: list[ChumpTag] = []
    for i, asset in enumerate(assets.value.children):
        if asset.type != TYPE_SOUP:
            continue
        assert isinstance(asset.value, ChumpSoup)
        raw = _kuid_from_tags(asset.value.children)
        if raw is None:
            raw = kuid_bin.parse_kuid_string(asset.name)
        if raw is None:
            continue
        children.append(ChumpTag.kuid(str(i), raw))
    ct = _find_child(chump.root, "contents-table")
    if ct is not None and ct.type == TYPE_SOUP:
        assert isinstance(ct.value, ChumpSoup)
        ct.value.children = children
    else:
        chump.root.insert(1, ChumpTag.soup("contents-table", children))


def _parse_tag(
    data: memoryview,
    pos: int,
    limit: int,
    *,
    parent: str,
    assets: list[CdpAsset],
    draft: _AssetDraft | None,
) -> int:
    if pos + 5 > limit:
        return limit
    tag_length = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    tag_end = min(pos + tag_length, limit)
    if pos >= tag_end:
        return tag_end

    name_size = int(data[pos])
    pos += 1
    if name_size < 1 or pos + name_size > tag_end:
        return tag_end
    name = bytes(data[pos : pos + name_size - 1]).decode("utf-8", errors="replace")
    pos += name_size  # name bytes + null

    if pos >= tag_end:
        return tag_end
    tag_type = int(data[pos])
    pos += 1

    if tag_type == 0:  # container
        if parent not in ("", "assets"):
            return tag_end
        child_draft = _AssetDraft() if parent == "assets" else draft
        while pos < tag_end:
            pos = _parse_tag(
                data,
                pos,
                tag_end,
                parent=name,
                assets=assets,
                draft=child_draft,
            )
        if parent == "assets" and child_draft is not None:
            assets.append(child_draft.finish())
        return tag_end

    value = bytes(data[pos:tag_end])
    if draft is None:
        return tag_end

    if tag_type == 1:  # int
        if name == "kuid" and len(value) >= 4:
            content = struct.unpack_from("<i", value, 0)[0]
            draft.kuid = kuid_bin.format_kuid(-1, content, None)
            draft._kuid_bytes = kuid_bin.pack_kuid(-1, content, None)
        elif name == "trainz-build" and len(value) >= 4:
            draft.trainz_build = str(struct.unpack_from("<i", value, 0)[0])
    elif tag_type == 2:  # float
        if name == "trainz-build" and len(value) >= 4:
            draft.trainz_build = f"{struct.unpack_from('<f', value, 0)[0]:g}"
    elif tag_type == 3:  # string
        text = value[:-1].decode("utf-8", errors="replace") if value else ""
        if name == "username":
            draft.username = text
        elif name == "kind":
            draft.kind = text
        elif name in ("category-region", "category-region-0"):
            draft.category_region = text
        elif name in ("category-era", "category-era-0"):
            draft.category_era = text
        elif name == "category-class":
            draft.category_class = text
        elif name == "description":
            draft.description = text
        elif name == "kuid":
            draft.kuid = text if "<" in text else f"<{text}>"
        elif name == "asset-filename" and draft.username == "Untitled":
            draft.username = text
    elif tag_type == 0x0D:  # kuid
        if name == "kuid" and len(value) >= 8:
            draft._kuid_bytes = value[:8]
            draft.kuid = kuid_bin.bytes_to_kuid(value[:8])

    return tag_end


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        asset = root / "asset"
        asset.mkdir()
        (asset / "config.txt").write_text(
            'username  "Demo"\nkind  "scenery"\nkuid  <kuid:1:2>\n',
            encoding="utf-8",
        )
        (asset / "note.txt").write_text("hello cdp", encoding="utf-8")
        nested = asset / "sub"
        nested.mkdir()
        (nested / "inner.bin").write_bytes(b"\x00\x01\x02" * 20)
        out = root / "demo.cdp"
        path, verdict = pack_asset_folders([asset], out)
        assert path.is_file()
        assert verdict.band == "ok"
        idx = open_cdp(path)
        assert len(idx.assets) == 1
        assert idx.assets[0].kuid == "<kuid:1:2>"
        dest = root / "out"
        written = extract_cdp(path, dest)
        assert any(p.name == "config.txt" for p in written)
        note = next(p for p in written if p.name == "note.txt")
        assert note.read_text(encoding="utf-8") == "hello cdp"
        ch = load_cdp(path)
        # temp .bak during overwrite — gone after success
        save_cdp(path, ch)
        bak = cdp_bak_path(path)
        assert not bak.is_file()
        replace_asset_config(
            ch, "<kuid:1:2>", 'username  "Demo2"\nkind  "scenery"\nkuid  <kuid:1:2>\n'
        )
        save_cdp(path, ch)
        assert not bak.is_file()
        # leftover from a failed write is cleared by discard
        bak.write_bytes(b"stale")
        assert discard_cdp_bak(path)
        assert not bak.is_file()
        nodes = browse_cdp(ch)
        assert nodes[0].files
        assert remove_file(ch, nodes[0].kuid, "note.txt")
        assert remove_asset(ch, nodes[0].kuid)
        print("cdp pack/extract self-check OK", format_bytes(path.stat().st_size))
