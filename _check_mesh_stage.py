"""ponytail: CDP mesh stage + Packages mesh_open hooks."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from trainz_studio.io.cdp import (
    is_mesh_preview_name,
    stage_asset_for_mesh_preview,
)
from trainz_studio.io.cdp_lzss import make_binary_blob
from trainz_studio.io.chump import (
    TYPE_RAW,
    TYPE_SOUP,
    ChumpFile,
    ChumpSoup,
    ChumpTag,
    text_to_chump,
)


def main() -> None:
    assert is_mesh_preview_name("body.trainzmesh")
    assert is_mesh_preview_name("a/b.texture.txt")
    assert not is_mesh_preview_name("x.wav")

    inner = text_to_chump('kind mesh\nusername "T"\n')
    raw = make_binary_blob(b"FBX test")
    files = ChumpTag(
        "files", TYPE_SOUP, ChumpSoup([ChumpTag("body.fbx", TYPE_RAW, raw)])
    )
    asset = ChumpTag(
        "<kuid:1:9>", TYPE_SOUP, ChumpSoup(list(inner.root) + [files])
    )
    chump = ChumpFile(root=[ChumpTag("assets", TYPE_SOUP, ChumpSoup([asset]))])
    dest = Path(tempfile.mkdtemp(prefix="tzs_stage_"))
    path = stage_asset_for_mesh_preview(
        chump, "<kuid:1:9>", dest, mesh_rel="body.fbx"
    )
    assert path.is_file() and path.read_bytes() == b"FBX test"

    app = QApplication.instance() or QApplication(sys.argv)
    from trainz_studio.ui.assets.packages import PackagesPage

    page = PackagesPage()
    assert hasattr(page, "btn_mesh_studio") and hasattr(page, "mesh_open")
    assert callable(getattr(page, "warm_fast_preview_infra", None))
    page.warm_fast_preview_infra()
    assert page._mesh_preview is not None
    print("ok")


if __name__ == "__main__":
    main()
