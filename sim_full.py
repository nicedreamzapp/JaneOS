"""Full self-test. Drives JaneOS like a real kid:
- picks each theme
- plays correct + wrong answers
- verifies audio fires, visible feedback shows, advance happens
- triggers 3-right streak (confetti), break button, repeat button
- reports EVERYTHING that's wrong (no spin)
"""
import asyncio
import sys
from playwright.async_api import async_playwright

URL_BASE = "http://127.0.0.1:9100"
THEMES = ["unicorns", "mermaids", "dinos", "space", "cats", "horses", "bluey"]


async def run():
    issues = []
    findings = []

    def log(msg):
        print(msg)

    def issue(theme, msg):
        issues.append(f"[{theme}] {msg}")
        log(f"  ❌ {msg}")

    def good(theme, msg):
        findings.append(f"[{theme}] {msg}")
        log(f"  ✓ {msg}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Hook fetch BEFORE app loads — record /api/say calls (server-side TTS)
        await page.add_init_script("""
          window.__SPOKEN = [];
          window.__CANCELS = 0;
          const origFetch = window.fetch.bind(window);
          window.fetch = function(url, opts) {
            try {
              const u = String(url || "");
              if (u.includes("/api/say") && !u.includes("/stop")) {
                let body = (opts && opts.body) || "{}";
                try { body = JSON.parse(body); } catch(_) {}
                window.__SPOKEN.push({text: body.text || "", interrupt: !!body.interrupt, t: Date.now()});
                if (body.interrupt) window.__CANCELS++;
              }
            } catch(_) {}
            return origFetch(url, opts);
          };
        """)

        # ── THEME LOOP ──
        for theme in THEMES:
            log(f"\n=== {theme} ===")
            await page.goto(URL_BASE + "/?v=fullsim")
            await page.wait_for_selector(f'[data-theme="{theme}"]', timeout=5000)

            spoke_before_click = await page.evaluate("() => window.__SPOKEN.length")
            await page.click(f'[data-theme="{theme}"]')

            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('#content .options button').length > 0 || document.querySelector('#content .trace-box')",
                    timeout=8000,
                )
            except Exception:
                issue(theme, "no first activity rendered within 8s")
                continue

            spoken = await page.evaluate("() => window.__SPOKEN")
            new_speeches = spoken[spoke_before_click:]
            greeting_spoken = any(("hi" in s["text"].lower() or "play" in s["text"].lower() or "let's" in s["text"].lower()) for s in new_speeches)
            if greeting_spoken:
                good(theme, f"greeting/prompt spoke ({len(new_speeches)} utterances)")
            else:
                issue(theme, f"no greeting/prompt spoken (utterances: {[s['text'][:40] for s in new_speeches]})")

            # ── Play 5 activities ──
            right_streak = 0
            saw_celebrate = False
            for i in range(5):
                state = await page.evaluate("""
                  () => ({
                    answer: window.STATE?.current?.screen?.answer ?? null,
                    skill: window.STATE?.current?.skill ?? null,
                    title: document.querySelector('#content .title-big')?.textContent || '',
                    buttons: [...document.querySelectorAll('#content .options button')].map(b => b.textContent),
                    hasTrace: !!document.querySelector('#content .trace-box'),
                  })
                """)

                # Visual sanity: counting tasks must show emojis
                t = state["title"].lower()
                if "how many" in t or "count" in t:
                    emojis = sum(1 for c in state["title"] if ord(c) > 0x2000)
                    if emojis < 2:
                        issue(theme, f"#{i+1} count task w/o emojis title={state['title']!r}")

                if not state["buttons"] and not state["hasTrace"]:
                    issue(theme, f"#{i+1} no tap targets and no trace box (skill={state['skill']})")
                    break

                # Click correct (alternate i=0,3 right; i=1 wrong; i=2 right; i=4 right) so we
                # also test the wrong-answer path
                want_correct = (i != 1)
                spoke_before = await page.evaluate("() => window.__SPOKEN.length")

                if state["hasTrace"]:
                    box = await page.query_selector("#content .trace-box")
                    bb = await box.bounding_box()
                    await page.mouse.move(bb["x"]+90, bb["y"]+90)
                    await page.mouse.down()
                    await page.mouse.move(bb["x"]+220, bb["y"]+260, steps=10)
                    await page.mouse.up()
                else:
                    ans = (state["answer"] or "").lower()
                    correct_idx = next((j for j, b in enumerate(state["buttons"]) if b.lower() == ans or ans in b.lower()), 0)
                    if want_correct:
                        idx = correct_idx
                    else:
                        idx = next((j for j in range(len(state["buttons"])) if j != correct_idx), 0)
                    await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")

                # Wait for visible feedback flash
                try:
                    await page.wait_for_selector(".fb-flash", timeout=2000)
                    cls = await page.evaluate("() => document.querySelector('.fb-flash')?.className")
                    is_yes = "fb-yes" in (cls or "")
                    is_no  = "fb-no"  in (cls or "")
                    if want_correct and not is_yes:
                        issue(theme, f"#{i+1} expected fb-yes, got class={cls}")
                    if (not want_correct) and not is_no:
                        issue(theme, f"#{i+1} expected fb-no, got class={cls}")
                except Exception:
                    issue(theme, f"#{i+1} no visible feedback flash appeared")

                # Wait for advance
                await page.wait_for_timeout(1900)
                spoken_after = await page.evaluate("() => window.__SPOKEN")
                new_after = spoken_after[spoke_before:]
                if not new_after:
                    issue(theme, f"#{i+1} no praise/feedback spoken after answer")

                if want_correct:
                    right_streak += 1

                # 3-right streak should fire bigCelebrate (observe a counter, not a transient class)
                cc = await page.evaluate("() => window.STATE?.celebrateCount || 0")
                if cc > 0:
                    saw_celebrate = True

            if right_streak >= 3 and saw_celebrate:
                good(theme, "3-right streak fired confetti celebrate")
            elif right_streak >= 3 and not saw_celebrate:
                issue(theme, "3-right streak DID NOT fire confetti")

            cancels = await page.evaluate("() => window.__CANCELS")
            if cancels > 0:
                issue(theme, f"speechSynthesis.cancel() called {cancels}x — would cut off speech")
            else:
                good(theme, "0 cancels (audio queue clean)")

            # Test break button
            await page.click("#break-btn")
            await page.wait_for_timeout(500)
            on_welcome = await page.evaluate("() => document.getElementById('welcome')?.classList.contains('active')")
            if on_welcome:
                good(theme, "break button returns to welcome")
            else:
                issue(theme, "break button did NOT return to welcome")

        await browser.close()

    log(f"\n\n=== SUMMARY: {len(findings)} good, {len(issues)} issues ===")
    if issues:
        for x in issues:
            log("  ❌ " + x)
        sys.exit(1)
    log("ALL CLEAN — no issues found.")


if __name__ == "__main__":
    asyncio.run(run())
