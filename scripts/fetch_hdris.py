"""Download CC0 Poly Haven HDRIs (prefer 2k .hdr) into assets/hdri/.

Run from repo root (trs22/):  python -m trainz_studio.scripts.fetch_hdris
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

# Mix of stunner outdoor skies + useful studios (CC0). Prefer puresky / scenic.
HDRIS = [
    # —— knock-out skies ——
    ("kloppenheim_06_puresky", "Kloppenheim Sky"),
    ("kloofendal_48d_partly_cloudy_puresky", "Kloofendal Cloudy"),
    ("drakensberg_solitary_mountain_puresky", "Drakensberg Peak"),
    ("belfast_sunset_puresky", "Belfast Sunset"),
    ("syferfontein_18d_clear_puresky", "Syferfontein Clear"),
    ("qwantani_noon", "Qwantani Noon"),
    ("autumn_field_puresky", "Autumn Field"),
    ("rosendal_plains_1", "Rosendal Plains"),
    ("spruit_sunrise", "Spruit Sunrise"),
    ("venice_sunset", "Venice Sunset"),
    ("industrial_sunset_puresky", "Industrial Sunset"),
    ("moonlit_golf", "Moonlit Night"),
    # —— studios (cabin lookdev) ——
    ("studio_small_09", "Studio Soft"),
    ("photo_studio_01", "Photo Studio"),
    ("brown_photostudio_02", "Brown Photostudio"),
]

from .. import PKG_ROOT

OUT = PKG_ROOT / "assets" / "hdri"
UA = {"User-Agent": "MSTN-MeshStudio/0.3 (dev; CC0 polyhaven)"}


def get_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def pick_hdri_url(files: dict) -> tuple[str | None, str]:
    """Prefer 2k .hdr, then 1k .hdr, then tonemapped jpg."""
    hdri = files.get("hdri") or {}
    for res in ("2k", "1k", "4k"):
        slot = hdri.get(res) or {}
        if "hdr" in slot:
            return slot["hdr"]["url"], "hdr"
    if "tonemapped" in files:
        return files["tonemapped"]["url"], "jpg"
    return None, "hdr"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for key, label in HDRIS:
        try:
            files = get_json(f"https://api.polyhaven.com/files/{key}")
        except Exception as e:
            print("FAIL api", key, e)
            continue
        url, ext = pick_hdri_url(files)
        if not url:
            print("NO FILE", key)
            continue
        # normalize key for rosendal (api id may be without _4k)
        dest = OUT / f"{key}.{ext}"
        stem_key = key
        if dest.exists() and dest.stat().st_size > 10_000:
            print("SKIP", dest.name)
        else:
            print("GET", key, f"({ext})")
            try:
                req = urllib.request.Request(url, headers=UA)
                data = urllib.request.urlopen(req, timeout=300).read()
                dest.write_bytes(data)
                print(" OK", len(data), "bytes ->", dest.name)
            except Exception as e:
                print("FAIL dl", key, e)
                continue
        manifest.append(
            {
                "key": stem_key,
                "label": label,
                "file": dest.name,
                "credit": "Poly Haven — CC0",
            }
        )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("DONE", len(manifest), "->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
