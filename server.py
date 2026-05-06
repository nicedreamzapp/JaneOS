"""JaneOS — adaptive AI tutor for Jane (1st grade).

Voice-driven learning playground on port 9100.
- Multi-theme (unicorns, dinos, mermaids, Bluey, space, cats, horses)
- 60-90s activity bursts with attention-drift detection
- Adaptive difficulty driven by per-skill mastery scores
- Lessons generated fresh by Claude API, with Ollama fallback
- Progress in local SQLite at data/jane.db
"""

import asyncio
import json
import os
import random
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path
from contextlib import suppress

import re
import aiohttp
from aiohttp import web

import activity_bank

# --- Config ---
PORT = 9100
JANEOS_DIR = Path(__file__).parent
STATIC_DIR = JANEOS_DIR / "static"
DATA_DIR = JANEOS_DIR / "data"
DB_PATH = DATA_DIR / "jane.db"
LLM_LABEL = "claude-cli (Max plan)"

# --- Tutor system prompt ---
TUTOR_PROMPT = """You are Jane's personal learning friend. Jane is in 1st grade and her attention span is short — keep everything punchy and joyful.

PERSONA
- Warm, playful, silly when it helps, always celebrating effort over outcome.
- Talk like a favorite kindergarten teacher who is also a little goofy.
- Use her name often. Never condescend. Never use baby talk.

OUTPUT RULES — MUST FOLLOW
- Always reply with ONE valid JSON object, no prose, no markdown fences.
- Schema:
  {
    "say": "text the tutor will SPEAK out loud (1-2 short sentences max)",
    "screen": {            // what to render on the screen
      "type": "word" | "image_word" | "math" | "story" | "phonics" | "celebrate" | "menu" | "trace" | "spell" | "free",
      "title": "...",      // optional big title
      "prompt": "...",     // optional secondary prompt
      "items": ["string", "string", ...], // ALWAYS array of plain strings (the click labels). For pictures, use emojis IN the string like "🦄 unicorn".
      "answer": "...",     // ground-truth answer for grading
      "theme": "unicorns" | "dinos" | "mermaids" | "bluey" | "space" | "cats" | "horses"
    },
    "expects": "tap" | "trace" | "none",   // internal token (frontend renders as click target either way)
    "skill": "phonics_cvc" | "sight_words" | "reading_fluency" | "math_count" | "math_add" | "math_sub" | "math_place_value" | "writing_letter" | "writing_sentence" | "science" | "sel" | "assessment" | "social",
    "difficulty": 1 | 2 | 3 | 4 | 5,
    "next_hint": "what kind of activity to do next, brief"
  }

ATTENTION-SPAN RULES
- Activities last 60-90 seconds. Keep instructions to 1 sentence.
- Switch modality every 1-2 activities (read -> count -> trace -> story -> phonics).
- Rotate themes she likes; never repeat the same theme twice in a row.
- After 3 wrong in a row: drop difficulty by 1 and say something encouraging.
- After 3 right in a row: bump difficulty by 1 and celebrate big.
- If she goes quiet, ask a silly question to re-engage.

ASSESSMENT (FIRST SESSION ONLY)
- For an unknown student, mix 5-7 quick checks across reading + math at increasing difficulty to find her level.
- Mark these activities with "skill": "assessment".

NEVER include emoji in "say" — they sound bad in TTS. Plain words only.
NEVER write more than 2 sentences in "say".
NEVER ask Jane to type — she's 6.
NEVER ask Jane to speak. She answers by CLICKING. Always provide an "items" array of 2-5 PLAIN STRINGS. "expects" must be "tap" or "trace" only (internal token — kid sees "click").
For free-response or trace activities (writing letters), set expects="trace" and answer to the target letter/word.
ALWAYS include a "difficulty" integer 1-5.

EXAMPLE valid output:
{"say":"Let's count! Click the right number.","screen":{"type":"math","title":"3 + 2 = ?","prompt":"Click the answer!","items":["4","5","6","7"],"answer":"5","theme":"unicorns"},"expects":"tap","skill":"math_add","difficulty":1,"next_hint":"sight word"}

CRITICAL — NEVER generate "math_count" activities. The system handles all counting tasks. Pick from: math_add, math_sub, math_place_value, sight_words, phonics_cvc, reading_fluency, science, social, sel.

CRITICAL — Whatever the kid is being asked to identify or count, that thing MUST appear visually in the title or items. Never say "how many stars?" without putting actual stars on screen — that confuses her. Use emojis IN the title to show what to count if needed.

CRITICAL — For MATH activities (skill starts with math_), the title is JUST the math expression, NOTHING ELSE. Examples: "3 + 2 = ?", "10 − 4 = ?", "13". Never prefix with theme emojis like "🚀 3 + 2 = ?".

CRITICAL — Phonics/sight-word titles are JUST the letter or word being practiced. Examples: "C...", "WHEN", "GOOD". Never decorative names like "Mermaid Magic" — the title must be the actual learning content.
"""


# --- DB ---
def db_init():
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        seconds_active INTEGER DEFAULT 0,
        activities_done INTEGER DEFAULT 0,
        theme TEXT
    );
    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        ts TEXT NOT NULL,
        skill TEXT NOT NULL,
        difficulty INTEGER,
        prompt TEXT,
        expected TEXT,
        got TEXT,
        correct INTEGER,
        latency_ms INTEGER,
        theme TEXT
    );
    CREATE TABLE IF NOT EXISTS mastery (
        skill TEXT PRIMARY KEY,
        score REAL NOT NULL DEFAULT 0,
        last_seen TEXT,
        attempts INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS prefs (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    # Seed prefs if empty
    cur.execute("INSERT OR IGNORE INTO prefs (key, value) VALUES ('name', 'Jane')")
    cur.execute("INSERT OR IGNORE INTO prefs (key, value) VALUES ('themes', ?)",
                (json.dumps(["unicorns", "dinos", "mermaids", "bluey", "space", "cats", "horses"]),))
    cur.execute("INSERT OR IGNORE INTO prefs (key, value) VALUES ('tutor_name', 'Bloom')")
    con.commit()
    con.close()


def db_conn():
    return sqlite3.connect(DB_PATH)


def get_pref(key, default=None):
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT value FROM prefs WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else default


def set_pref(key, value):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO prefs (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    con.commit()
    con.close()


def record_attempt(session_id, skill, difficulty, prompt, expected, got, correct, latency_ms, theme):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO attempts (session_id, ts, skill, difficulty, prompt, expected, got, correct, latency_ms, theme) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, datetime.utcnow().isoformat(), skill, difficulty, prompt, expected, got,
         1 if correct else 0, latency_ms, theme),
    )
    # Update mastery — exponential moving average
    cur.execute("SELECT score, attempts, correct FROM mastery WHERE skill=?", (skill,))
    row = cur.fetchone()
    alpha = 0.25  # how fast mastery moves
    target = 1.0 if correct else 0.0
    if row is None:
        cur.execute(
            "INSERT INTO mastery (skill, score, last_seen, attempts, correct) VALUES (?, ?, ?, 1, ?)",
            (skill, target, datetime.utcnow().isoformat(), 1 if correct else 0),
        )
    else:
        new_score = row[0] + alpha * (target - row[0])
        cur.execute(
            "UPDATE mastery SET score=?, last_seen=?, attempts=attempts+1, correct=correct+? WHERE skill=?",
            (new_score, datetime.utcnow().isoformat(), 1 if correct else 0, skill),
        )
    con.commit()
    con.close()


def mastery_summary():
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT skill, score, attempts, correct, last_seen FROM mastery ORDER BY score ASC")
    rows = cur.fetchall()
    con.close()
    return [
        {"skill": r[0], "score": round(r[1], 3), "attempts": r[2], "correct": r[3], "last_seen": r[4]}
        for r in rows
    ]


def session_start(theme):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO sessions (started_at, theme) VALUES (?, ?)",
        (datetime.utcnow().isoformat(), theme),
    )
    sid = cur.lastrowid
    con.commit()
    con.close()
    return sid


def session_end(sid, seconds, activities):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "UPDATE sessions SET ended_at=?, seconds_active=?, activities_done=? WHERE id=?",
        (datetime.utcnow().isoformat(), seconds, activities, sid),
    )
    con.commit()
    con.close()


# --- LLM ---
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/Users/matthewmacosko/.local/bin/claude")
CLAUDE_MODEL_FLAG = os.environ.get("JANEOS_CLAUDE_MODEL", "haiku")  # haiku|sonnet|opus


async def call_claude(messages, system):
    """Call Claude via the Claude Code CLI (Max plan, OAuth) — NOT the billed API.
    Combines messages into a single prompt and shells out to `claude --print`.
    Strips ANTHROPIC_API_KEY from the env so the CLI uses OAuth, not the API key.
    """
    parts = []
    for m in messages:
        role = m.get("role", "user").upper()
        parts.append(f"{role}:\n{m.get('content','')}")
    full = (system + "\n\n" if system else "") + "\n\n".join(parts)

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    def run():
        return subprocess.run(
            [CLAUDE_BIN, "--print", "--model", CLAUDE_MODEL_FLAG, full],
            capture_output=True, text=True, timeout=60, env=env,
        )

    proc = await asyncio.get_event_loop().run_in_executor(None, run)
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(f"claude cli rc={proc.returncode}: {proc.stderr[:300]}")
    return (proc.stdout or "").strip()


# (Ollama removed 2026-05-05 — claude CLI is the only LLM path. Bank handles offline.)


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF]"
)


def _strip_emoji(s):
    if not isinstance(s, str):
        return s
    return _EMOJI_RE.sub("", s).replace("  ", " ").strip()


def _validate_activity(p):
    """Return (ok, reason). Enforces the schema strictly."""
    if not isinstance(p, dict):
        return False, "not a dict"
    if not isinstance(p.get("say"), str) or not p["say"].strip():
        return False, "missing say"
    screen = p.get("screen")
    if not isinstance(screen, dict):
        return False, "missing screen"
    if p.get("expects") not in ("tap", "trace", "none"):
        return False, f"bad expects: {p.get('expects')}"
    if p.get("expects") == "tap":
        items = screen.get("items")
        if not isinstance(items, list) or len(items) < 2:
            return False, f"click needs >=2 items, got {items!r}"
        for it in items:
            if not isinstance(it, str):
                return False, f"non-string item {it!r}"
        if "answer" not in screen:
            return False, "click needs answer"
    if not p.get("skill"):
        return False, "no skill"
    try:
        d = int(p.get("difficulty", 0))
        if not (1 <= d <= 5):
            return False, f"bad difficulty {d}"
    except Exception:
        return False, "bad difficulty"
    return True, "ok"


def _normalize_activity(p):
    """Clean up an LLM response in place (strip emojis, default theme, etc.)."""
    if not isinstance(p, dict):
        return p
    if isinstance(p.get("say"), str):
        p["say"] = _strip_emoji(p["say"])
    return p


async def llm(messages, system=TUTOR_PROMPT):
    """Call Claude. (Ollama removed — bank handles offline fallback.)"""
    last_err = None
    for fn in (call_claude,):
        try:
            text = await fn(messages, system)
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
        except Exception as e:
            last_err = e
            print(f"[llm] {fn.__name__} failed: {e}")
            continue
    raise RuntimeError(f"all LLMs failed: {last_err}")


# --- Pre-generation queue ---
# A short queue of LLM-generated activities, refilled in background, consumed by /api/next.
# Keeps the kid waiting at most milliseconds even when the LLM is slow.
_QUEUE: asyncio.Queue = None
_QUEUE_TASK = None
_TARGET_QUEUE_SIZE = 3
_LLM_HEALTHY = True
_LLM_LAST_FAIL = 0


async def _llm_one_activity(theme_pin=None):
    """Generate one activity using LLM, with current student state."""
    name = get_pref("name", "Jane")
    fav = theme_pin or get_pref("favorite_theme")
    mastery = mastery_summary()
    weak = [m["skill"] for m in mastery if m["score"] < 0.5][:5]
    strong = [m["skill"] for m in mastery if m["score"] > 0.85][:5]
    is_first = len(mastery) < 3
    msg = f"""STUDENT: {name}, age 6, 1st grade.
THEME: {fav or 'pick one of unicorns/mermaids/dinos/space/cats/horses/bluey'}
WEAK_SKILLS: {weak or 'unknown — assess first'}
STRONG_SKILLS: {strong or 'unknown'}
ASSESSMENT_MODE: {is_first}

Output ONE 60-90s click activity in the JSON schema. Items must be plain strings."""
    p = await llm([{"role": "user", "content": msg}])
    p = _normalize_activity(p)
    ok, reason = _validate_activity(p)
    if not ok:
        raise RuntimeError(f"bad activity: {reason}")
    return p


async def _queue_filler():
    """Background task: keep the queue full of pre-generated activities."""
    global _QUEUE, _LLM_HEALTHY, _LLM_LAST_FAIL
    consecutive_failures = 0
    while True:
        try:
            if _QUEUE.qsize() < _TARGET_QUEUE_SIZE:
                p = await _llm_one_activity()
                await _QUEUE.put(p)
                if not _LLM_HEALTHY:
                    print("[queue] LLM recovered, queue resuming")
                _LLM_HEALTHY = True
                consecutive_failures = 0
            else:
                await asyncio.sleep(0.5)
        except Exception as e:
            consecutive_failures += 1
            _LLM_LAST_FAIL = time.time()
            if _LLM_HEALTHY and consecutive_failures >= 2:
                print(f"[queue] LLM marked unhealthy after {consecutive_failures} failures: {e}")
                _LLM_HEALTHY = False
            # Back off increasingly when failing — try again every 30s instead of pounding
            await asyncio.sleep(min(30, 2 * consecutive_failures))


# --- Routes ---
async def index(req):
    return web.FileResponse(STATIC_DIR / "index.html")


async def parent(req):
    return web.FileResponse(STATIC_DIR / "parent.html")


async def api_state(req):
    return web.json_response({
        "name": get_pref("name", "Jane"),
        "tutor_name": get_pref("tutor_name", "Bloom"),
        "themes": json.loads(get_pref("themes", '["unicorns"]')),
        "favorite_theme": get_pref("favorite_theme"),
        "mastery": mastery_summary(),
        "model": LLM_LABEL,
    })


async def api_pref(req):
    body = await req.json()
    for k, v in body.items():
        set_pref(k, v if isinstance(v, str) else json.dumps(v))
    return web.json_response({"ok": True})


async def api_session_start(req):
    body = await req.json()
    sid = session_start(body.get("theme"))
    return web.json_response({"session_id": sid})


async def api_session_end(req):
    body = await req.json()
    session_end(body["session_id"], body.get("seconds", 0), body.get("activities", 0))
    return web.json_response({"ok": True})


async def api_attempt(req):
    body = await req.json()
    record_attempt(
        body.get("session_id"),
        body["skill"],
        body.get("difficulty", 1),
        body.get("prompt", ""),
        body.get("expected", ""),
        body.get("got", ""),
        body.get("correct", False),
        body.get("latency_ms", 0),
        body.get("theme"),
    )
    return web.json_response({"ok": True})


async def api_next(req):
    """Return the next activity. Fast: queue-first, fall back to bank instantly."""
    body = await req.json()
    history = body.get("history", [])
    theme_pin = body.get("theme") or get_pref("favorite_theme")

    # Pick what skill we want next: prefer weakest skill, mix in random for variety
    mastery = mastery_summary()
    weak = [m["skill"] for m in mastery if m["score"] < 0.6]
    target_skill = random.choice(weak) if weak and random.random() < 0.5 else None

    # 1) Try the LLM queue with a tiny timeout — if we have one ready, use it
    if _QUEUE is not None and not _QUEUE.empty():
        try:
            p = _QUEUE.get_nowait()
            # Re-validate at serve time (themes change, schema may have stale items)
            ok, _ = _validate_activity(p)
            if ok:
                if theme_pin and isinstance(p.get("screen"), dict):
                    p["screen"]["theme"] = theme_pin
                return web.json_response(p)
        except asyncio.QueueEmpty:
            pass

    # 2) Wait for queue briefly only if LLM is healthy (otherwise bank wins immediately)
    if _QUEUE is not None and _LLM_HEALTHY:
        try:
            p = await asyncio.wait_for(_QUEUE.get(), timeout=0.1)
            ok, _ = _validate_activity(p)
            if ok:
                if theme_pin and isinstance(p.get("screen"), dict):
                    p["screen"]["theme"] = theme_pin
                return web.json_response(p)
        except asyncio.TimeoutError:
            pass

    # 3) Bank fallback — INSTANT, always works, even offline
    recent_titles = {h.get("prompt", "") for h in history if h.get("prompt")}
    p = activity_bank.serve(skill=target_skill, theme=theme_pin, exclude_titles=recent_titles)
    return web.json_response(p)


async def api_grade(req):
    """Loose grading via LLM — answers spoken aloud are messy.
    Body: { expected, got, skill }"""
    body = await req.json()
    expected = body.get("expected", "").strip().lower()
    got = body.get("got", "").strip().lower()
    skill = body.get("skill", "")

    # Cheap exact match first
    if got and (got == expected or expected in got or got in expected):
        return web.json_response({"correct": True, "feedback": "exact"})

    # Number normalization for math
    nums = {"zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5",
            "six":"6","seven":"7","eight":"8","nine":"9","ten":"10",
            "eleven":"11","twelve":"12","thirteen":"13","fourteen":"14",
            "fifteen":"15","sixteen":"16","seventeen":"17","eighteen":"18",
            "nineteen":"19","twenty":"20"}
    norm_got = "".join(c for c in got if c.isdigit()) or nums.get(got.split()[-1] if got else "", "")
    if norm_got and norm_got == expected:
        return web.json_response({"correct": True, "feedback": "number-normalized"})

    # Otherwise ask LLM
    sys = "You judge whether a 6-year-old's spoken answer is correct. Be generous on pronunciation. Return only JSON: {\"correct\": true|false, \"feedback\": \"one short kind sentence\"}"
    msg = f"Skill: {skill}\nExpected answer: {expected}\nWhat she said: {got}\nIs that right?"
    try:
        result = await llm([{"role": "user", "content": msg}], system=sys)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"correct": False, "feedback": "Try again, sweetie!", "_err": str(e)})


async def api_mastery(req):
    return web.json_response({"mastery": mastery_summary()})


# --- Server-side TTS (macOS `say`) ---
# Browser speechSynthesis in Brave/Chromium is unreliable. Using the OS-native
# `say` command guarantees real audio playback through Mac speakers using the
# actual macOS Premium voices.
_TTS_VOICE_FILE = JANEOS_DIR / "voices" / os.environ.get("JANEOS_VOICE", "en_US-amy-medium.onnx")
_TTS_QUEUE: asyncio.Queue = None
_TTS_TASK = None
_TTS_VOICE_OBJ = None  # PiperVoice singleton
_TTS_PLAYBACK_PROC: subprocess.Popen | None = None  # currently-playing afplay


def _load_piper():
    """Load Piper voice once at startup."""
    global _TTS_VOICE_OBJ
    try:
        from piper.voice import PiperVoice
        _TTS_VOICE_OBJ = PiperVoice.load(str(_TTS_VOICE_FILE))
        print(f"[tts] piper loaded: {_TTS_VOICE_FILE.name} sr={_TTS_VOICE_OBJ.config.sample_rate}")
    except Exception as e:
        print(f"[tts] piper load FAILED: {e}")
        _TTS_VOICE_OBJ = None


def _synth_to_wav(text: str, out_path: str):
    """Synthesize text to WAV file using Piper. Blocking."""
    import wave
    if _TTS_VOICE_OBJ is None:
        return False
    with wave.open(out_path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_TTS_VOICE_OBJ.config.sample_rate)
        _TTS_VOICE_OBJ.synthesize_wav(text, wav)
    return True


async def _tts_worker():
    """Single consumer: synth with piper, then play with afplay. Strictly serial."""
    global _TTS_PLAYBACK_PROC
    import tempfile
    loop = asyncio.get_event_loop()
    while True:
        try:
            item = await _TTS_QUEUE.get()
            if item is None:
                continue
            text = item["text"]
            if not text:
                continue
            # 1) synth WAV (offline, fast — ~200ms for short phrase on M4)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
            ok = await loop.run_in_executor(None, _synth_to_wav, text, wav_path)
            if not ok:
                try: os.unlink(wav_path)
                except Exception: pass
                continue
            # 2) play and wait
            def play():
                p = subprocess.Popen(
                    ["/usr/bin/afplay", wav_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return p
            _TTS_PLAYBACK_PROC = await loop.run_in_executor(None, play)
            try:
                await loop.run_in_executor(None, lambda: _TTS_PLAYBACK_PROC.wait(timeout=30))
            except Exception:
                pass
            _TTS_PLAYBACK_PROC = None
            try: os.unlink(wav_path)
            except Exception: pass
        except Exception as e:
            print(f"[tts_worker] {e}")
            await asyncio.sleep(0.2)


def _tts_clear_and_stop():
    global _TTS_PLAYBACK_PROC
    if _TTS_QUEUE is not None:
        while not _TTS_QUEUE.empty():
            try: _TTS_QUEUE.get_nowait()
            except Exception: break
    if _TTS_PLAYBACK_PROC and _TTS_PLAYBACK_PROC.poll() is None:
        try: _TTS_PLAYBACK_PROC.terminate()
        except Exception: pass
    # kill any orphan playback
    try:
        subprocess.run(["/usr/bin/pkill", "-x", "afplay"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    except Exception:
        pass


async def api_say(req):
    """Synthesize text and return WAV bytes — browser plays them.
    Optionally dumps each WAV to disk with a timestamp for post-process video assembly."""
    import wave, io
    body = await req.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.Response(status=400, text="no text")
    clean = "".join(c for c in text if ord(c) < 0x2000 or c in " \n\t").strip()
    if _TTS_VOICE_OBJ is None:
        return web.Response(status=503, text="tts not loaded")

    def synth():
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2)
            wav.setframerate(_TTS_VOICE_OBJ.config.sample_rate)
            _TTS_VOICE_OBJ.synthesize_wav(clean, wav)
        return buf.getvalue()

    data = await asyncio.get_event_loop().run_in_executor(None, synth)

    # Optional: dump WAVs with relative-to-start timestamp for video recording
    dump_dir = os.environ.get("JANEOS_TTS_DUMP")
    if dump_dir:
        try:
            os.makedirs(dump_dir, exist_ok=True)
            stamp_file = os.path.join(dump_dir, "_t0.txt")
            if not os.path.exists(stamp_file):
                with open(stamp_file, "w") as f:
                    f.write(str(time.time()))
                t0 = time.time()
            else:
                t0 = float(open(stamp_file).read().strip())
            offset = time.time() - t0
            wav_path = os.path.join(dump_dir, f"{offset:08.3f}.wav")
            with open(wav_path, "wb") as f:
                f.write(data)
            with open(os.path.join(dump_dir, "manifest.txt"), "a") as f:
                f.write(f"{offset:.3f}\t{clean}\n")
        except Exception as e:
            print(f"[tts dump] {e}")

    return web.Response(
        body=data,
        headers={
            "content-type": "audio/wav",
            "cache-control": "no-cache",
            "x-voice": _TTS_VOICE_FILE.name,
        },
    )


async def api_say_stop(req):
    return web.json_response({"ok": True})


async def api_health(req):
    return web.json_response({
        "ok": True,
        "model": LLM_LABEL,
        "llm_healthy": _LLM_HEALTHY,
        "queue_size": _QUEUE.qsize() if _QUEUE else 0,
        "db": str(DB_PATH),
        "uptime_s": int(time.time() - START_TIME),
    })


# --- App ---
START_TIME = time.time()


async def _on_startup(app):
    global _QUEUE, _QUEUE_TASK, _TTS_QUEUE, _TTS_TASK
    _QUEUE = asyncio.Queue(maxsize=_TARGET_QUEUE_SIZE)
    _QUEUE_TASK = asyncio.create_task(_queue_filler())
    _TTS_QUEUE = asyncio.Queue()
    _load_piper()
    _TTS_TASK = asyncio.create_task(_tts_worker())
    _tts_clear_and_stop()
    print(f"[JaneOS] background LLM queue running (target size {_TARGET_QUEUE_SIZE})")
    print(f"[JaneOS] tts worker running, voice={_TTS_VOICE_FILE.name}")
    print(f"[JaneOS] activity bank: {activity_bank.stats()}")


async def _on_cleanup(app):
    global _QUEUE_TASK, _TTS_TASK
    if _QUEUE_TASK:
        _QUEUE_TASK.cancel()
    if _TTS_TASK:
        _TTS_TASK.cancel()
    _tts_clear_and_stop()


def make_app():
    db_init()
    app = web.Application()
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/parent", parent)
    app.router.add_get("/api/health", api_health)
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/pref", api_pref)
    app.router.add_post("/api/session/start", api_session_start)
    app.router.add_post("/api/session/end", api_session_end)
    app.router.add_post("/api/attempt", api_attempt)
    app.router.add_post("/api/next", api_next)
    app.router.add_post("/api/grade", api_grade)
    app.router.add_get("/api/mastery", api_mastery)
    app.router.add_post("/api/say", api_say)
    app.router.add_post("/api/say/stop", api_say_stop)
    app.router.add_static("/static/", STATIC_DIR)
    return app


if __name__ == "__main__":
    print(f"[JaneOS] starting on :{PORT}")
    print(f"[JaneOS] model: {LLM_LABEL}")
    print(f"[JaneOS] db:    {DB_PATH}")
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None)
