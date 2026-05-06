"""Browser-level simulator: drives JaneOS through Playwright like a kid would.
Verifies that what's on the screen actually matches what the tutor is asking.
Catches: 'count X' without emojis, blank screens, broken renderers.
"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:9100/"
THEMES = ["unicorns", "mermaids", "dinos", "space", "cats", "horses", "bluey"]
ACTIVITIES_PER_THEME = 6


COUNT_WORDS = ("count", "how many", "how-many")


def is_emoji_or_pictogram(c):
    o = ord(c)
    # Rough pictogram/emoji ranges
    return (0x1F300 <= o <= 0x1FAFF) or (0x2600 <= o <= 0x27BF) or (0x1F600 <= o <= 0x1F6FF)


async def run():
    failures = []
    activities = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        for theme in THEMES:
            print(f"\n=== theme: {theme} ===")
            await page.goto(URL + "?v=test")
            await page.wait_for_selector(f'[data-theme="{theme}"]', timeout=5000)
            # Stub out speak to avoid TTS waits
            await page.evaluate("window.speechSynthesis.cancel(); window.speak = () => Promise.resolve();")
            await page.click(f'[data-theme="{theme}"]')
            await page.wait_for_timeout(800)

            for i in range(ACTIVITIES_PER_THEME):
                # Wait until either content has options, or a trace box, or text in bubble
                try:
                    await page.wait_for_function("""
                        () => {
                          const c = document.getElementById("content");
                          if (!c) return false;
                          const opts = c.querySelectorAll(".options button");
                          const trace = c.querySelector(".trace-box");
                          return opts.length > 0 || trace;
                        }
                    """, timeout=8000)
                except Exception as e:
                    failures.append({"theme": theme, "step": i, "err": f"timed out waiting for content: {e}"})
                    print(f"  #{i+1} TIMEOUT")
                    break

                # Verify TTS actually spoke + visible feedback flashed on grade
                # (only after first activity)
                  () => {
                    const said = document.getElementById("said")?.textContent?.trim() || "";
                    const titleEl = document.querySelector("#content .title-big");
                    const title = titleEl?.textContent?.trim() || "";
                    const promptEl = document.querySelector("#content .prompt-line");
                    const prompt = promptEl?.textContent?.trim() || "";
                    const buttons = [...document.querySelectorAll("#content .options button")].map(b => b.textContent);
                    const hasTrace = !!document.querySelector("#content .trace-box");
                    const expected = window.STATE?.current?.screen?.answer ?? null;
                    const skill = window.STATE?.current?.skill ?? null;
                    const screenType = window.STATE?.current?.screen?.type ?? null;
                    return {said, title, prompt, buttons, hasTrace, expected, skill, screenType};
                  }
                """)

                full = f"{state['said']} {state['title']} {state['prompt']}".lower()
                # Check for "count X" / "how many X" without emojis in title
                problems = []
                if any(w in full for w in COUNT_WORDS):
                    emojis = [c for c in state["title"] if is_emoji_or_pictogram(c)]
                    if len(emojis) < 2:
                        problems.append(f"asks to count but title has {len(emojis)} emojis")

                if not state["buttons"] and not state["hasTrace"]:
                    problems.append("no buttons and no trace box")

                # answer/skill aren't always exposed cleanly to JS in time; we skip those checks
                # and focus on UX-visible bugs (count without emojis, blank screens).
                if state["expected"] not in (None, "") and state["buttons"] and not state["hasTrace"]:
                    e = (state["expected"] or "").lower()
                    if not any(e in b.lower() or b.lower() in e for b in state["buttons"]):
                        problems.append(f"answer {state['expected']!r} not among buttons {state['buttons']}")

                ok = "OK" if not problems else "FAIL"
                sk = str(state['skill'] or '?')
                ti = str(state['title'] or '')[:30]
                print(f"  #{i+1:>2} {ok} skill={sk:<22} title={ti!r:<32} btns={state['buttons']}")
                if problems:
                    print(f"        ↳ {problems}")
                    print(f"        ↳ said={state['said']!r}")
                    failures.append({"theme": theme, "step": i, "state": state, "problems": problems})

                activities.append({"theme": theme, "step": i, "state": state, "problems": problems})

                # Click the right answer (or any option) to advance
                if state["hasTrace"]:
                    box = await page.query_selector("#content .trace-box")
                    if box:
                        bb = await box.bounding_box()
                        if bb:
                            await page.mouse.move(bb["x"]+80, bb["y"]+80)
                            await page.mouse.down()
                            await page.mouse.move(bb["x"]+200, bb["y"]+220, steps=10)
                            await page.mouse.up()
                    await page.wait_for_timeout(1200)
                elif state["buttons"]:
                    e = (state["expected"] or "").lower()
                    target_index = 0
                    for idx, b in enumerate(state["buttons"]):
                        if b.lower() == e or e in b.lower():
                            target_index = idx; break
                    # Click via JS to avoid stale-element issues
                    await page.evaluate(f"""
                      (() => {{
                        const btns = document.querySelectorAll("#content .options button");
                        if (btns[{target_index}]) btns[{target_index}].click();
                      }})()
                    """)
                    await page.wait_for_timeout(1200)

        await browser.close()

    total = len(activities)
    passed = total - len(failures)
    print(f"\n=== summary: {passed}/{total} OK; {len(failures)} failed ===")
    if failures:
        for f in failures[:10]:
            print(f"  - {f['theme']} step {f['step']}: {f.get('problems') or f.get('err')}")
        sys.exit(1)
    print("ALL CLEAN")


if __name__ == "__main__":
    asyncio.run(run())
