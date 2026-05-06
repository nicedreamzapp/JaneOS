"""End-to-end simulator: pretends to be Jane playing JaneOS.
Runs a full session, posts attempts, verifies schema, prints latencies.
Run: ./.venv/bin/python sim.py
"""
import asyncio
import json
import random
import sys
import time

import aiohttp

BASE = "http://127.0.0.1:9100"
N_ACTIVITIES = 8


async def main():
    print(f"[sim] hitting {BASE}")
    async with aiohttp.ClientSession() as s:
        # Health
        async with s.get(f"{BASE}/api/health") as r:
            assert r.status == 200, f"health {r.status}"
            h = await r.json()
            print(f"[sim] health: claude={h['claude']} model={h['model']}")

        # State
        async with s.get(f"{BASE}/api/state") as r:
            st = await r.json()
            print(f"[sim] state: name={st['name']} mastery_count={len(st['mastery'])}")

        # Start session
        async with s.post(f"{BASE}/api/session/start", json={"theme": "unicorns"}) as r:
            sid = (await r.json())["session_id"]
            print(f"[sim] session_id={sid}")

        history = []
        latencies = []
        bad = []

        for i in range(N_ACTIVITIES):
            t0 = time.time()
            async with s.post(f"{BASE}/api/next", json={"history": history[-6:]}) as r:
                if r.status != 200:
                    print(f"[sim] /api/next FAIL {r.status}: {await r.text()}")
                    bad.append(("next", r.status))
                    continue
                p = await r.json()
            dt_ms = int(1000 * (time.time() - t0))
            latencies.append(dt_ms)

            # Schema checks
            problems = []
            if not isinstance(p.get("say"), str) or not p["say"]:
                problems.append("missing 'say'")
            screen = p.get("screen", {})
            if p.get("expects") not in ("tap", "trace", "none"):
                problems.append(f"bad expects: {p.get('expects')}")
            if p.get("expects") == "tap":
                items = screen.get("items")
                if not isinstance(items, list) or len(items) < 2:
                    problems.append(f"tap with bad items: {items}")
                else:
                    for it in items:
                        if not isinstance(it, str):
                            problems.append(f"non-string item: {it!r}")
                            break
                if "answer" not in screen:
                    problems.append("missing answer for tap")
            if p.get("skill") in (None, ""):
                problems.append("missing skill")
            if not (1 <= int(p.get("difficulty", 0)) <= 5):
                problems.append(f"bad difficulty: {p.get('difficulty')}")

            ok = "OK" if not problems else "FAIL"
            print(f"[sim] #{i+1} {dt_ms:>4}ms {ok:<4} skill={p.get('skill')!s:<22} expects={p.get('expects')} d={p.get('difficulty')} | say={p.get('say','')[:60]!r}")
            if problems:
                print(f"      ↳ {problems}")
                print(f"      ↳ items={screen.get('items')}")
                bad.append(("schema", problems))

            # Simulate Jane: 70% correct
            answer = str(screen.get("answer", ""))
            items = screen.get("items", [])
            correct = random.random() < 0.7
            if correct and answer:
                got = answer
            elif items and isinstance(items, list) and isinstance(items[0], str):
                wrongs = [x for x in items if x != answer]
                got = random.choice(wrongs) if wrongs else (items[0] if items else "?")
            else:
                got = "wrong"

            # Grade
            async with s.post(f"{BASE}/api/grade",
                              json={"expected": answer, "got": got, "skill": p.get("skill")}) as r:
                g = await r.json()

            # Record attempt
            await s.post(f"{BASE}/api/attempt", json={
                "session_id": sid,
                "skill": p.get("skill"),
                "difficulty": p.get("difficulty"),
                "prompt": screen.get("title", ""),
                "expected": answer,
                "got": got,
                "correct": bool(g.get("correct")),
                "theme": "unicorns",
            })
            history.append({"skill": p.get("skill"), "correct": bool(g.get("correct")), "difficulty": p.get("difficulty")})

        # End session
        await s.post(f"{BASE}/api/session/end", json={"session_id": sid, "seconds": 90, "activities": N_ACTIVITIES})

        # Mastery snapshot
        async with s.get(f"{BASE}/api/mastery") as r:
            m = await r.json()
        print(f"\n[sim] mastery touched: {len(m['mastery'])} skills")
        for row in m["mastery"][:8]:
            print(f"      {row['skill']:<22} score={row['score']:.2f} attempts={row['attempts']} correct={row['correct']}")

        # Summary
        avg = sum(latencies)/len(latencies) if latencies else 0
        print(f"\n[sim] latency: avg={avg:.0f}ms min={min(latencies, default=0)}ms max={max(latencies, default=0)}ms")
        print(f"[sim] failures: {len(bad)}")
        if bad:
            sys.exit(1)
        print("[sim] PASS")


if __name__ == "__main__":
    asyncio.run(main())
