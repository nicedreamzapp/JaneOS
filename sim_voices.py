"""See what voices Chromium (== Brave's engine) actually has access to."""
import asyncio
from playwright.async_api import async_playwright


async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto("about:blank")
        # voices populate async — wait
        await page.evaluate("""
          () => new Promise(res => {
            if (speechSynthesis.getVoices().length) return res();
            speechSynthesis.onvoiceschanged = () => res();
            setTimeout(res, 1000);
          })
        """)
        voices = await page.evaluate("""
          () => speechSynthesis.getVoices().map(v => ({
            name: v.name, lang: v.lang, default: v.default, local: v.localService
          }))
        """)
        print(f"Total: {len(voices)}")
        for v in voices:
            mark = " (default)" if v["default"] else ""
            mark += " (local)" if v["local"] else " (cloud)"
            print(f"  {v['lang']:<8} {v['name']}{mark}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
