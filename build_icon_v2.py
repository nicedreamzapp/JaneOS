"""Render the unicorn icon via Playwright, resize to iconset sizes, and convert to .icns."""
import asyncio
import subprocess
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
HTML = ROOT / "icon_design.html"
OUT = ROOT / "build" / "icon.iconset"
OUT.mkdir(parents=True, exist_ok=True)


async def render_master():
    master = OUT / "_master.png"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1024, "height": 1024}, device_scale_factor=2)
        await page.goto("file://" + str(HTML))
        await page.wait_for_timeout(800)
        el = await page.query_selector(".icon")
        await el.screenshot(path=str(master), omit_background=True)
        await browser.close()
    return master


def make_iconset(master: Path):
    img = Image.open(master).convert("RGBA")
    targets = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for name, sz in targets:
        out = OUT / name
        resized = img.resize((sz, sz), Image.LANCZOS)
        resized.save(out, "PNG")
        print(f"  {name} ({sz}x{sz})")


async def main():
    master = await render_master()
    print(f"master rendered → {master}")
    make_iconset(master)
    icns = ROOT / "build" / "JaneOS.icns"
    subprocess.run(["iconutil", "-c", "icns", str(OUT), "-o", str(icns)], check=True)
    print(f"icns → {icns}")


if __name__ == "__main__":
    asyncio.run(main())
