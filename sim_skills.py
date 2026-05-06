"""Per-skill self-test. Forces JaneOS to serve one of every activity type and
verifies it renders + grades + advances correctly.
"""
import asyncio
import sys
from playwright.async_api import async_playwright

URL_BASE = "http://127.0.0.1:9100"
SKILLS = ["math_count", "math_add", "math_sub", "math_place_value",
          "sight_words", "phonics_cvc", "reading_fluency",
          "science", "social", "sel", "writing_letter"]


async def run():
    issues = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.add_init_script("""
          window.__SPOKEN = [];
          const origSpeak = window.speechSynthesis.speak.bind(window.speechSynthesis);
          window.speechSynthesis.speak = function(u){window.__SPOKEN.push({text: String(u.text||'')}); setTimeout(()=>{try{u.onend&&u.onend()}catch(_){}}, 5); return origSpeak(u);};
        """)
        await page.goto(URL_BASE + "/?v=skills")
        await page.click('[data-theme="unicorns"]')
        await page.wait_for_function("() => document.querySelectorAll('#content .options button').length>0 || document.querySelector('#content .trace-box')")

        # Cycle through API calls to find each skill once. We can't directly request a skill;
        # bank rotates, so we just play 80 activities and verify all skills appear with sane state.
        seen = {}
        broken = []
        for i in range(80):
            state = await page.evaluate("""
              () => ({
                skill: window.STATE?.current?.skill,
                screenType: window.STATE?.current?.screen?.type,
                title: document.querySelector('#content .title-big')?.textContent || '',
                prompt: document.querySelector('#content .prompt-line')?.textContent || '',
                buttons: [...document.querySelectorAll('#content .options button')].map(b => b.textContent),
                hasTrace: !!document.querySelector('#content .trace-box'),
                answer: window.STATE?.current?.screen?.answer ?? null,
                said: document.getElementById('said')?.textContent || '',
              })
            """)
            sk = state["skill"] or "?"
            if sk not in seen:
                seen[sk] = state
                # Validate per-skill expectations
                problems = []
                if sk == "writing_letter":
                    if not state["hasTrace"]:
                        problems.append("trace box missing")
                else:
                    if not state["buttons"]:
                        problems.append("no buttons")
                    if state["answer"] in (None, ""):
                        problems.append("no answer")
                def is_pictogram(c):
                    o = ord(c)
                    return (0x1F300 <= o <= 0x1FAFF) or (0x2600 <= o <= 0x27BF) or (0x1F600 <= o <= 0x1F6FF)
                if sk.startswith("math_count"):
                    emojis = sum(1 for c in state["title"] if is_pictogram(c))
                    if emojis < 2:
                        problems.append(f"count title has {emojis} emojis")
                if sk.startswith("math_") and sk != "math_count":
                    if any(is_pictogram(c) for c in state["title"]):
                        problems.append(f"math title has emojis: {state['title']!r}")
                if not state["said"]:
                    problems.append("bubble text empty")

                # Visible click feedback test
                if state["hasTrace"]:
                    box = await page.query_selector("#content .trace-box")
                    bb = await box.bounding_box()
                    await page.mouse.move(bb["x"]+90, bb["y"]+90)
                    await page.mouse.down()
                    await page.mouse.move(bb["x"]+220, bb["y"]+260, steps=10)
                    await page.mouse.up()
                else:
                    ans = (state["answer"] or "").lower()
                    idx = next((j for j, b in enumerate(state["buttons"]) if b.lower() == ans or ans in b.lower()), 0)
                    await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")
                try:
                    await page.wait_for_selector(".fb-flash", timeout=1500)
                except Exception:
                    problems.append("no feedback flash on correct click")
                await page.wait_for_timeout(1300)

                if problems:
                    broken.append((sk, problems, state))
                    print(f"  ❌ {sk:<22} {problems}  title={state['title'][:30]!r}")
                else:
                    print(f"  ✓ {sk:<22} title={state['title'][:30]!r:<32} btns={state['buttons']}")
            else:
                # Just advance through to find new skills
                if state["hasTrace"]:
                    box = await page.query_selector("#content .trace-box")
                    bb = await box.bounding_box()
                    await page.mouse.move(bb["x"]+90, bb["y"]+90)
                    await page.mouse.down()
                    await page.mouse.move(bb["x"]+220, bb["y"]+260, steps=8)
                    await page.mouse.up()
                elif state["buttons"]:
                    ans = (state["answer"] or "").lower()
                    idx = next((j for j, b in enumerate(state["buttons"]) if b.lower() == ans or ans in b.lower()), 0)
                    await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")
                await page.wait_for_timeout(1100)

            if len(seen) >= len(SKILLS):
                break

        not_seen = [s for s in SKILLS if s not in seen and s not in ("assessment",)]
        print()
        for ns in not_seen:
            print(f"  ⚠️  never saw skill: {ns}")
        print(f"\nSaw {len(seen)} skills, {len(broken)} had issues.")
        if broken or not_seen:
            sys.exit(1)
        await browser.close()
    print("ALL SKILLS CLEAN")


if __name__ == "__main__":
    asyncio.run(run())
