"""End-to-end audio + feedback sim.
Verifies: TTS queue fires utterances, visible feedback flash appears, auto-advance works.
"""
import asyncio
import sys
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:9100/?simaudio=1"


async def run():
    fails = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Hook speechSynthesis BEFORE the app loads — record every utterance
        await page.add_init_script("""
          window.__SPOKEN = [];
          const origSpeak = window.speechSynthesis.speak.bind(window.speechSynthesis);
          window.speechSynthesis.speak = function(u) {
            window.__SPOKEN.push({text: String(u.text), volume: u.volume, rate: u.rate});
            // Synthesize an immediate onend so promises resolve in headless
            setTimeout(() => { try { u.onend && u.onend(); } catch(_){} }, 5);
            return origSpeak(u);
          };
          const origCancel = window.speechSynthesis.cancel.bind(window.speechSynthesis);
          window.__CANCEL_COUNT = 0;
          window.speechSynthesis.cancel = function() {
            window.__CANCEL_COUNT++;
            return origCancel();
          };
        """)

        await page.goto(URL)
        await page.wait_for_selector('[data-theme="unicorns"]')

        # Click theme — should trigger primeAudio + greeting + first activity speech
        await page.click('[data-theme="unicorns"]')
        await page.wait_for_function("() => document.querySelectorAll('#content .options button').length > 0", timeout=10000)

        spoken = await page.evaluate("() => window.__SPOKEN || []")
        cancels = await page.evaluate("() => window.__CANCEL_COUNT || 0")
        print(f"[boot] spoke {len(spoken)} times, cancels: {cancels}")
        for s in spoken:
            print(f"   '{s['text'][:80]}' vol={s['volume']} rate={s['rate']}")

        if not any("Hi" in s["text"] or "play" in s["text"].lower() for s in spoken):
            fails.append("greeting not spoken")
        if cancels > 0:
            fails.append(f"cancel called {cancels}x — kills queued speech")

        # Click correct answer — should see feedback flash + praise speech + auto-advance
        before_count = len(spoken)
        state = await page.evaluate("""
          () => ({
            answer: window.STATE?.current?.screen?.answer,
            buttons: [...document.querySelectorAll("#content .options button")].map(b => b.textContent),
          })
        """)
        if state["answer"] and state["buttons"]:
            ans = state["answer"].lower()
            idx = next((i for i, b in enumerate(state["buttons"]) if b.lower() == ans or ans in b.lower()), 0)
            await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")

            # Wait for visible feedback to appear
            try:
                await page.wait_for_selector(".fb-flash", timeout=2000)
                fb_text = await page.evaluate("() => document.querySelector('.fb-flash')?.textContent")
                fb_class = await page.evaluate("() => document.querySelector('.fb-flash')?.className")
                print(f"[grade] flash: '{fb_text}' class={fb_class}")
            except Exception:
                fails.append("no visible feedback flash on correct answer")

            await page.wait_for_timeout(1500)
            spoken_after = await page.evaluate("() => window.__SPOKEN || []")
            new_speeches = spoken_after[before_count:]
            print(f"[grade] {len(new_speeches)} new utterances after click:")
            for s in new_speeches:
                print(f"   '{s['text'][:80]}'")
            if not new_speeches:
                fails.append("no praise spoken after correct answer")

            # Verify auto-advance: by now activity should have changed
            new_state = await page.evaluate("""
              () => ({
                buttons: [...document.querySelectorAll("#content .options button")].map(b => b.textContent),
                title: document.querySelector("#content .title-big")?.textContent || ""
              })
            """)
            if new_state["buttons"] == state["buttons"]:
                fails.append("activity did not auto-advance after grade")
            else:
                print(f"[grade] advanced to: title={new_state['title'][:30]!r} btns={new_state['buttons']}")

        await browser.close()

    print()
    if fails:
        for f in fails:
            print(f"  FAIL: {f}")
        sys.exit(1)
    print("ALL CLEAN")


if __name__ == "__main__":
    asyncio.run(run())
