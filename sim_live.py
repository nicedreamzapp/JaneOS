"""Live demo — opens a visible browser window and plays through 6 activities.
Audio comes from server-side Piper, so Mac speakers will play during the demo.
"""
import asyncio
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:9100/?demo=1"


async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        await page.goto(URL)
        await page.wait_for_selector('[data-theme="unicorns"]')

        print("Demo starting — watch the window + listen.")
        await page.click('[data-theme="unicorns"]')

        for i in range(6):
            # wait for activity to render
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('#content .options button').length>0 || document.querySelector('#content .trace-box')",
                    timeout=10000,
                )
            except Exception:
                print(f"  #{i+1}  no activity rendered, skipping")
                continue

            # Let the kid see + hear the question
            await page.wait_for_timeout(4500)

            state = await page.evaluate("""
              () => ({
                ans: window.STATE?.current?.screen?.answer || "",
                btns: [...document.querySelectorAll('#content .options button')].map(b => b.textContent),
                hasTrace: !!document.querySelector('#content .trace-box'),
                say: window.STATE?.current?.say || "",
                skill: window.STATE?.current?.skill || "",
              })
            """)
            print(f"  #{i+1}  skill={state['skill']:<20} | {state['say'][:60]}")

            wrong_one = (i == 1)  # demo a wrong answer once

            if state["hasTrace"]:
                box = await page.query_selector("#content .trace-box")
                bb = await box.bounding_box()
                await page.mouse.move(bb["x"]+90, bb["y"]+90)
                await page.mouse.down()
                await page.mouse.move(bb["x"]+220, bb["y"]+260, steps=12)
                await page.mouse.up()
            elif state["btns"]:
                ans = state["ans"].lower()
                ci = next((j for j, b in enumerate(state["btns"]) if b.lower() == ans or ans in b.lower()), 0)
                idx = (ci + 1) % len(state["btns"]) if wrong_one else ci
                await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")

            # let praise/feedback play, then advance
            await page.wait_for_timeout(2500)

        await page.wait_for_timeout(1500)
        # back to home
        await page.click("#break-btn")
        await page.wait_for_timeout(2000)
        await browser.close()
        print("Demo done.")


if __name__ == "__main__":
    asyncio.run(run())
