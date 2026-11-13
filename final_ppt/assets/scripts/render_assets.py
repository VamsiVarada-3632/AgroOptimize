"""Render SVG diagrams and HTML snapshots to high-resolution PNG (2x) and PDF with headless Chrome.

Requires playwright (pip install playwright) and an installed Google Chrome (channel="chrome").
Usage: python final_ppt/assets/scripts/render_assets.py <file.svg|file.html> [...]
Writes <name>.png and <name>.pdf next to each input.
"""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def size(path: Path):
    m = re.search(r'<svg[^>]*width="(\d+)"[^>]*height="(\d+)"', path.read_text())
    return (int(m.group(1)), int(m.group(2))) if m else (1600, 900)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    for arg in sys.argv[1:]:
        src = Path(arg).resolve()
        w, h = size(src) if src.suffix == ".svg" else (1600, 900)
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        if src.suffix == ".svg":
            page.set_content("<!doctype html><html><body style='margin:0;background:#fcfcfb'>" + src.read_text() + "</body></html>")
        else:
            page.goto(src.as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=str(src.with_suffix(".png")), full_page=True, timeout=120000)
        dims = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
        page.pdf(path=str(src.with_suffix(".pdf")), width=f"{dims[0]}px", height=f"{dims[1] + 2}px", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        page.close()
        print("rendered", src.with_suffix(".png").name, src.with_suffix(".pdf").name)
    browser.close()
