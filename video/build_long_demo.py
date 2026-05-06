"""Build a 10-minute kid-watchable gameplay video.

Strategy:
  1) Set JANEOS_TTS_DUMP env var so server saves every WAV with timestamp
  2) Open Playwright (1920x1080 video recording), drive ~10 min of gameplay
  3) Build aligned audio track from saved WAVs at their offsets
  4) Mix in soft background music
  5) Add title card listing what the game teaches
  6) Concat: title card + gameplay
"""
import asyncio, os, subprocess, time, wave
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path("/Users/matthewmacosko/Desktop/PROJECTS/JaneOS")
VID = ROOT / "video"
BUILD = VID / "build_long"
BUILD.mkdir(parents=True, exist_ok=True)
TTS_DIR = BUILD / "tts_dump"

W, H = 1920, 1080
FPS = 30
TARGET_SECONDS = 600  # 10 minutes


def step(msg): print(f"\n[LONG] {msg}")
def run(args, **kw):
    print("       $", " ".join(str(a) for a in args[:6]) + (" ..." if len(args) > 6 else ""))
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("ERR:", r.stderr[-500:])
        raise RuntimeError("cmd fail")
    return r


async def render_card(html_file, duration, out_mp4):
    png = BUILD / f"{html_file.stem}.png"
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=2)
        p = await ctx.new_page()
        await p.goto("file://" + str(html_file))
        await p.wait_for_timeout(700)
        await p.screenshot(path=str(png))
        await b.close()
    n = max(1, int(round(duration * FPS)))
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(png),
         "-frames:v", str(n), "-vf", f"scale={W}:{H}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-b:v", "5500k", "-maxrate", "5500k", "-bufsize", "10M", "-preset", "slow",
         str(out_mp4)])


async def record_gameplay():
    rec_dir = BUILD / "rec"
    rec_dir.mkdir(exist_ok=True)
    for f in rec_dir.glob("*"): f.unlink()
    # Reset TTS dump
    if TTS_DIR.exists():
        for f in TTS_DIR.iterdir(): f.unlink()
    TTS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(rec_dir),
            record_video_size={"width": W, "height": H},
        )
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:9100/?long=1")
        await page.wait_for_selector('[data-theme="unicorns"]')
        await page.wait_for_timeout(1500)

        # Sweep theme cards
        cards = await page.query_selector_all(".theme-card")
        for c in cards[:6]:
            try: await c.hover()
            except Exception: pass
            await page.wait_for_timeout(350)

        # Pick first theme
        themes = ["unicorns", "mermaids", "dinos", "space", "cats", "horses", "bluey"]
        theme_idx = 0
        await page.click(f'[data-theme="{themes[theme_idx]}"]')

        start = time.time()
        questions = 0
        while (time.time() - start) < TARGET_SECONDS:
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('#content .options button').length>0 || document.querySelector('#content .trace-box')",
                    timeout=10000,
                )
            except Exception:
                # mid-load hiccup — break briefly
                await page.wait_for_timeout(1000)
                continue
            await page.wait_for_timeout(2400)
            state = await page.evaluate("""
              () => ({
                ans: window.STATE?.current?.screen?.answer || "",
                btns: [...document.querySelectorAll('#content .options button')].map(b => b.textContent),
                hasTrace: !!document.querySelector('#content .trace-box'),
              })
            """)
            # Mostly correct; occasional miss to show wrong feedback
            want_correct = (questions % 7 != 3)
            if state["hasTrace"]:
                box = await page.query_selector("#content .trace-box")
                bb = await box.bounding_box()
                if bb:
                    await page.mouse.move(bb["x"]+bb["width"]/4, bb["y"]+bb["height"]/4)
                    await page.mouse.down()
                    await page.mouse.move(bb["x"]+3*bb["width"]/4, bb["y"]+3*bb["height"]/4, steps=10)
                    await page.mouse.up()
            elif state["btns"]:
                ans = (state["ans"] or "").lower()
                ci = next((j for j, b in enumerate(state["btns"]) if b.lower() == ans or ans in b.lower()), 0)
                idx = ci if want_correct else (ci + 1) % len(state["btns"])
                await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")
            await page.wait_for_timeout(1700)
            questions += 1
            # Every ~25 questions, switch themes for visual variety
            if questions % 25 == 0:
                await page.click("#break-btn")
                await page.wait_for_timeout(800)
                theme_idx = (theme_idx + 1) % len(themes)
                await page.click(f'[data-theme="{themes[theme_idx]}"]')

        await ctx.close()
        await b.close()
    webm = next(rec_dir.glob("*.webm"))
    return webm, time.time() - start, questions


def build_audio_track(total_seconds: float, out_wav: Path):
    """Compose: silence + WAV at offset + silence + WAV at offset, etc., from TTS_DIR."""
    manifest = TTS_DIR / "manifest.txt"
    if not manifest.exists():
        print("  no TTS manifest — building silence track")
        run(["ffmpeg", "-y", "-f", "lavfi",
             "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
             "-t", f"{total_seconds:.3f}",
             "-acodec", "pcm_s16le", str(out_wav)])
        return
    entries = []
    for line in manifest.read_text().splitlines():
        parts = line.split("\t")
        if len(parts) < 2: continue
        try:
            offset = float(parts[0])
            entries.append(offset)
        except ValueError:
            continue
    print(f"  building audio with {len(entries)} TTS entries spanning {total_seconds:.1f}s")

    # Build by concatenating: silence(gap) + line.wav + silence(gap) + ...
    parts = []
    last_end = 0.0
    for offset in entries:
        wav = TTS_DIR / f"{offset:08.3f}.wav"
        if not wav.exists():
            continue
        with wave.open(str(wav), "rb") as w:
            dur = w.getnframes() / w.getframerate()
        gap = max(0.0, offset - last_end)
        if gap > 0.001:
            sil = BUILD / f"sil_{len(parts):04d}.wav"
            run(["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
                 "-t", f"{gap:.3f}", "-acodec", "pcm_s16le", str(sil)])
            parts.append(sil)
        # Force consistent format
        norm = BUILD / f"norm_{len(parts):04d}.wav"
        run(["ffmpeg", "-y", "-i", str(wav),
             "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1", str(norm)])
        parts.append(norm)
        last_end = offset + dur
    # tail silence
    if total_seconds > last_end:
        tail = BUILD / "sil_tail.wav"
        run(["ffmpeg", "-y", "-f", "lavfi",
             "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
             "-t", f"{total_seconds - last_end:.3f}",
             "-acodec", "pcm_s16le", str(tail)])
        parts.append(tail)
    listf = BUILD / "audio_list.txt"
    listf.write_text("\n".join(f"file '{p}'" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
         "-c:a", "pcm_s16le", str(out_wav)])


def mix_with_music(narration_wav: Path, total_seconds: float, out_wav: Path):
    music = ROOT / "video" / "build" / "music_Wallpaper.mp3"
    if not music.exists():
        # just copy narration
        run(["ffmpeg", "-y", "-i", str(narration_wav), "-c:a", "pcm_s16le", str(out_wav)])
        return
    run([
        "ffmpeg", "-y",
        "-i", str(narration_wav),
        "-stream_loop", "-1", "-i", str(music),
        "-filter_complex",
        ("[0:a]aresample=22050,volume=1.0[narr];"
         "[1:a]aresample=22050,volume=0.10[bgm];"
         "[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0[mixed]"),
        "-map", "[mixed]",
        "-acodec", "pcm_s16le", "-ar", "22050",
        str(out_wav),
    ])


async def main():
    step("1) record continuous 10-min gameplay")
    webm, real_dur, questions = await record_gameplay()
    print(f"   recorded {real_dur:.1f}s, {questions} questions")

    step("2) build aligned audio track from server WAV dumps")
    narration = BUILD / "narration.wav"
    build_audio_track(real_dur, narration)

    step("3) mix with soft background music")
    mixed_audio = BUILD / "mixed_audio.wav"
    mix_with_music(narration, real_dur, mixed_audio)

    step("4) gameplay webm → mp4 (capped to actual recorded duration)")
    gameplay_mp4 = BUILD / "gameplay.mp4"
    n = max(1, int(round(real_dur * FPS)))
    run(["ffmpeg", "-y", "-i", str(webm),
         "-frames:v", str(n), "-vf", f"scale={W}:{H}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "10M", "-preset", "fast",
         "-an", str(gameplay_mp4)])

    step("5) render title card")
    title_mp4 = BUILD / "title.mp4"
    await render_card(VID / "long_title.html", 5.0, title_mp4)

    step("6) concat title + gameplay")
    full_video = BUILD / "full_video.mp4"
    listf = BUILD / "video_list.txt"
    listf.write_text("\n".join(f"file '{p}'" for p in [title_mp4, gameplay_mp4]))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-b:v", "4500k", "-maxrate", "4500k", "-bufsize", "10M", "-preset", "fast", "-an",
         str(full_video)])

    step("7) prepend silent audio for title duration, then mux")
    title_silence = BUILD / "title_silence.wav"
    run(["ffmpeg", "-y", "-f", "lavfi",
         "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
         "-t", "5.0", "-acodec", "pcm_s16le", str(title_silence)])
    full_audio = BUILD / "full_audio.wav"
    listf2 = BUILD / "fullaudio_list.txt"
    listf2.write_text(f"file '{title_silence}'\nfile '{mixed_audio}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf2),
         "-c:a", "pcm_s16le", str(full_audio)])

    final = VID / "JaneOS_long_demo.mp4"
    run(["ffmpeg", "-y", "-i", str(full_video), "-i", str(full_audio),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
         str(final)])
    print(f"\n✓ → {final}")
    print(f"  size: {final.stat().st_size/1024/1024:.2f} MB")
    print(f"  duration: ~{(real_dur + 5):.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
