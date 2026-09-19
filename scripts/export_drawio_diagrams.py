#!/usr/bin/env python3
"""Export the repository's draw.io diagrams to PNG.

Renderer order:
  1. draw.io desktop CLI (``drawio`` on PATH or the macOS app bundle) — offline.
  2. Headless Chrome + the official draw.io viewer (needs network access to
     viewer.diagrams.net). Override the browser with ``CHROME_BIN``.

Usage:
    uv run python scripts/export_drawio_diagrams.py              # all diagrams
    uv run python scripts/export_drawio_diagrams.py 03-request-path
"""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, unquote

from PIL import Image, ImageChops
from PIL.PngImagePlugin import PngInfo

ROOT = Path(__file__).resolve().parents[1]
# (draw.io sources, PNG output) pairs
DIAGRAM_DIRS = (
    (ROOT / "articles" / "diagrams", ROOT / "articles" / "assets"),
    (ROOT / "docs" / "diagrams", ROOT / "docs" / "assets"),
)

SCALE = 2  # 2x pixels so Medium's 680px column stays crisp
MARGIN = 20  # CSS px of white space kept around the drawing
VIEWER_JS = "https://viewer.diagrams.net/js/viewer-static.min.js"

DRAWIO_APP = "/Applications/draw.io.app/Contents/MacOS/draw.io"
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


def find_drawio_cli() -> str | None:
    found = shutil.which("drawio")
    if found:
        return found
    return DRAWIO_APP if os.path.isfile(DRAWIO_APP) else None


def find_chrome() -> str:
    candidates = [os.environ.get("CHROME_BIN", ""), *CHROME_CANDIDATES]
    for cand in candidates:
        if not cand:
            continue
        path = cand if os.path.isabs(cand) else shutil.which(cand)
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError("No draw.io CLI or Chrome/Chromium found (set CHROME_BIN)")


def diagram_size(xml: str) -> tuple[int, int]:
    """Bounding box of top-level vertices (children of layer ``1``)."""
    root = ET.fromstring(xml)
    max_x = max_y = 0.0
    for cell in root.iter("mxCell"):
        if cell.get("vertex") != "1" or cell.get("parent") != "1":
            continue
        geo = cell.find("mxGeometry")
        if geo is None:
            continue
        x, y = float(geo.get("x", 0)), float(geo.get("y", 0))
        max_x = max(max_x, x + float(geo.get("width", 0)))
        max_y = max(max_y, y + float(geo.get("height", 0)))
    return int(max_x) + 1, int(max_y) + 1


def autocrop(png: Path) -> None:
    """Trim to the drawing and keep a uniform white margin."""
    img = Image.open(png).convert("RGB")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bbox = ImageChops.difference(img, bg).getbbox()
    if bbox is None:
        raise RuntimeError(f"{png.name}: rendered an empty image")
    pad = MARGIN * SCALE
    left, top, right, bottom = bbox
    cropped = img.crop((left, top, right, bottom))
    out = Image.new("RGB", (cropped.width + 2 * pad, cropped.height + 2 * pad), (255, 255, 255))
    out.paste(cropped, (pad, pad))
    out.save(png)


def render_with_chrome(chrome: str, xml: str, out_png: Path) -> None:
    width, height = diagram_size(xml)
    config = {"xml": xml, "toolbar": "", "nav": False, "lightbox": False, "resize": True}
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#fff}</style></head><body>"
        f"<div class='mxgraph' data-mxgraph=\"{html.escape(json.dumps(config))}\"></div>"
        f"<script src='{VIEWER_JS}'></script></body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        page_path = Path(tmp) / "diagram.html"
        page_path.write_text(page, encoding="utf-8")
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            # No --user-data-dir: headless already uses a throwaway profile, and a
            # custom one keeps Chrome alive after the screenshot on macOS.
            f"--force-device-scale-factor={SCALE}",
            f"--window-size={width + 160},{height + 160}",
            "--virtual-time-budget=20000",
            f"--screenshot={out_png}",
            page_path.as_uri(),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    autocrop(out_png)


def render_with_cli(cli: str, src: Path, out_png: Path) -> None:
    cmd = [cli, "-x", "-f", "png", "-s", str(SCALE), "-b", str(MARGIN), "-o", str(out_png), str(src)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def embed_source(png: Path, xml: str) -> None:
    """Write the draw.io XML into the PNG the same way draw.io does (tEXt 'mxfile')."""
    img = Image.open(png)
    img.load()
    info = PngInfo()
    info.add_text("mxfile", quote(xml, safe="-_.!~*'()"))
    img.save(png, pnginfo=info, optimize=True)
    check = Image.open(png)
    if unquote(check.text.get("mxfile", "")) != xml:
        raise RuntimeError(f"{png.name}: embedded draw.io source did not round-trip")


def export(src: Path, out_dir: Path, cli: str | None, chrome: str | None) -> Path:
    xml = src.read_text(encoding="utf-8")
    out_png = out_dir / f"{src.stem}.png"
    if cli:
        render_with_cli(cli, src, out_png)
    else:
        render_with_chrome(chrome or find_chrome(), xml, out_png)
    embed_source(out_png, xml)
    return out_png


def main(argv: list[str]) -> int:
    names = set(argv)
    jobs = [
        (src, out_dir)
        for src_dir, out_dir in DIAGRAM_DIRS
        for src in sorted(src_dir.glob("*.drawio"))
        if not names or src.stem in names
    ]
    if not jobs:
        where = ", ".join(str(s.relative_to(ROOT)) for s, _ in DIAGRAM_DIRS)
        print(f"No .drawio files matched in {where}", file=sys.stderr)
        return 1
    cli = find_drawio_cli()
    chrome = None if cli else find_chrome()
    print(f"renderer: {'draw.io CLI' if cli else 'headless Chrome + draw.io viewer'}")
    for src, out_dir in jobs:
        out_dir.mkdir(parents=True, exist_ok=True)
        out = export(src, out_dir, cli, chrome)
        with Image.open(out) as img:
            print(f"  {src.name} -> {out.relative_to(ROOT)} ({img.width}x{img.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
