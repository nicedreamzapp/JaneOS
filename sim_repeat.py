"""Test the repeat / say-again button."""
import asyncio
import sys
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:9100/?v=repeat"


async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.add_init_script("""
          window.__SPOKEN = [];
          const origSpeak = window.speechSynthesis.speak.bind(window.speechSynthesis);
          window.speechSynthesis.speak = function(u){
            window.__SPOKEN.push({text: String(u.text||''), t: Date.now()});
            setTimeout(()=>{try{u.onend&&u.onend()}catch(_){}}, 5);
            return origSpeak(u);
          };
        """)
        await page.goto(URL)
        await page.click('[data-theme="unicorns"]')
        await page.wait_for_function("() => document.querySelectorAll('#content .options button').length>0")

        # capture state before pressing repeat
        before = await page.evaluate("() => ({spoken: window.__SPOKEN.length, last: window.STATE?.lastSpoken})")
        print(f"before repeat click: {before}")

        # locate the repeat button
        rb = await page.query_selector("#repeat-btn")
        if not rb:
            print("FAIL: #repeat-btn not in DOM"); sys.exit(1)
        bb = await rb.bounding_box()
        visible = await rb.is_visible()
        print(f"repeat-btn: visible={visible}, bbox={bb}, text={(await rb.text_content())!r}")

        # Click via DOM (button might be off-screen or behind keyboard)
        await page.evaluate("document.getElementById('repeat-btn').click()")
        await page.wait_for_timeout(500)

        after = await page.evaluate("() => ({spoken: window.__SPOKEN.length, last: window.__SPOKEN.at(-1)?.text})")
        print(f"after repeat click: {after}")

        if after["spoken"] > before["spoken"] and after["last"] == before["last"]:
            print("✓ repeat works — re-spoke the last utterance")
        elif after["spoken"] > before["spoken"]:
            print(f"⚠️  spoke something but text differs: {after['last']!r} vs {before['last']!r}")
        else:
            print("❌ repeat did not trigger any new speech")
            sys.exit(1)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
