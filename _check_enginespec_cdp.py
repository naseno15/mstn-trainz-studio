"""ponytail: assert enginespec CDP round-trip helpers (run: python -m trainz_studio._check_enginespec_cdp)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from trainz_studio.io.cdp import asset_config_text, replace_asset_config  # noqa: E402
from trainz_studio.io.chump import (  # noqa: E402
    TYPE_SOUP,
    ChumpFile,
    ChumpSoup,
    ChumpTag,
    text_to_chump,
)
from trainz_studio.lib.engine_tuner.config_io import (  # noqa: E402
    config_to_text,
    load_config_from_text,
    looks_like_enginespec,
)

SAMPLE = """
kuid                                    <kuid:1:2>
kind                                    enginespec
username                                "Test Spec"
trainz-build                            4.6
throttle-power {
  0                                     0
  1                                     1000
}
"""

# traincar that *mentions* enginespec in kuid-table must NOT open Engine Tuner
TRAINCAR = """
kuid                                    <kuid:9:9>
kind                                    traincar
username                                "Daewoo"
kuid-table {
  enginespec                            <kuid:1:2>
}
"""


def main() -> None:
    assert looks_like_enginespec(SAMPLE)
    assert not looks_like_enginespec(TRAINCAR)
    cfg = load_config_from_text(SAMPLE)
    text = config_to_text(cfg)
    assert looks_like_enginespec(text)
    assert "throttle-power" in text

    inner = text_to_chump(SAMPLE)
    asset = ChumpTag("<kuid:1:2>", TYPE_SOUP, ChumpSoup(list(inner.root)))
    chump = ChumpFile(root=[ChumpTag("assets", TYPE_SOUP, ChumpSoup([asset]))])

    got = asset_config_text(chump, "<kuid:1:2>")
    assert looks_like_enginespec(got)

    tuned = config_to_text(load_config_from_text(SAMPLE))
    replace_asset_config(chump, "<kuid:1:2>", tuned)
    again = asset_config_text(chump, "<kuid:1:2>")
    assert looks_like_enginespec(again)
    assert "Test Spec" in again or "enginespec" in again.lower()

    # Packages Save text on config.txt uses the same replace_asset_config path
    edited = SAMPLE.replace("Test Spec", "Edited Spec")
    replace_asset_config(chump, "<kuid:1:2>", edited)
    assert "Edited Spec" in asset_config_text(chump, "<kuid:1:2>")
    print("_check_enginespec_cdp: ok")


if __name__ == "__main__":
    main()
