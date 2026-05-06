"""Build a polished, narration-synced demo video for JaneOS.

Architecture:
  1) ONE continuous Playwright gameplay recording (no scene re-inits).
     - lingers on welcome, hovers themes, picks unicorn, plays 5 activities,
       hits the 3-right streak for confetti, shows variety.
     - we record CHECKPOINT TIMESTAMPS during recording so narration can sync.
  2) Synth narration broken into per-checkpoint lines, padded/timed to land at
     each visual moment.
  3) Bookend with intro logo + outro logo cards.
  4) Mux: video stream = [intro card] + [gameplay] + [outro card]
          audio stream = [silence to match intro] + [synced narration over gameplay] + [silence/closing line over outro]
"""
import asyncio
import os
import subprocess
import time
import wave
from pathlib import Path
from playwright.async_api import async_playwright
from piper.voice import PiperVoice

ROOT = Path("/Users/matthewmacosko/Desktop/PROJECTS/JaneOS")
VID = ROOT / "video"
BUILD = VID / "build"
BUILD.mkdir(parents=True, exist_ok=True)
W, H = 1280, 720
FPS = 30


def step(msg):
    print(f"\n[BUILD] {msg}")


def run(args, **kw):
    pretty = " ".join(str(a) for a in args[:6]) + (" ..." if len(args) > 6 else "")
    print("       $", pretty)
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("ERR:", r.stderr[-400:])
        raise RuntimeError("cmd failed")
    return r


# ── continuous gameplay ──
async def record_gameplay(out_dir: Path):
    """Drive JaneOS in one shot. Returns (webm_path, checkpoints)
    where checkpoints maps name → seconds-from-start at which the moment landed.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*"):
        f.unlink()

    checkpoints = {}
    t0 = None

    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(out_dir),
            record_video_size={"width": W, "height": H},
        )
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:9100/?v=demo")
        await page.wait_for_selector('[data-theme="unicorns"]')
        t0 = time.time()
        def stamp(name):
            checkpoints[name] = time.time() - t0

        # SCENE 1 — brief welcome screen
        stamp("welcome_in")
        await page.wait_for_timeout(1100)  # was 2.4s — trimmed

        # SCENE 2 — quick theme hover sweep (3s, was 6s)
        cards = await page.query_selector_all(".theme-card")
        stamp("themes_hover")
        # only hover the first 4 cards quickly
        for c in cards[:4]:
            try: await c.hover()
            except Exception: pass
            await page.wait_for_timeout(300)
        await page.wait_for_timeout(300)

        # SCENE 3 — pick unicorns
        stamp("pick_unicorns")
        await page.click('[data-theme="unicorns"]')
        await page.wait_for_function(
            "() => document.querySelectorAll('#content .options button').length>0 || document.querySelector('#content .trace-box')",
            timeout=8000,
        )

        async def play_one(label, want_correct=True):
            # wait for activity to render
            await page.wait_for_function(
                "() => document.querySelectorAll('#content .options button').length>0 || document.querySelector('#content .trace-box')",
                timeout=8000,
            )
            stamp(f"q_{label}")
            await page.wait_for_timeout(2200)  # let her "read" the question
            state = await page.evaluate("""
              () => ({
                ans: window.STATE?.current?.screen?.answer || "",
                btns: [...document.querySelectorAll('#content .options button')].map(b => b.textContent),
                hasTrace: !!document.querySelector('#content .trace-box'),
              })
            """)
            if state["hasTrace"]:
                box = await page.query_selector("#content .trace-box")
                bb = await box.bounding_box()
                await page.mouse.move(bb["x"]+90, bb["y"]+90); await page.mouse.down()
                await page.mouse.move(bb["x"]+220, bb["y"]+260, steps=10); await page.mouse.up()
            elif state["btns"]:
                ans = (state["ans"] or "").lower()
                ci = next((j for j, b in enumerate(state["btns"]) if b.lower() == ans or ans in b.lower()), 0)
                idx = ci if want_correct else (ci + 1) % len(state["btns"])
                await page.evaluate(f"document.querySelectorAll('#content .options button')[{idx}].click()")
            stamp(f"a_{label}")
            await page.wait_for_timeout(1700)  # green flash + sticker pop time

        # 6 distinct activities — every screen is different content
        await play_one("1", True)
        await play_one("2", True)
        # streak reaches 3 → bigCelebrate fires after this answer
        await play_one("3", True)
        stamp("celebrate")
        await page.wait_for_timeout(2200)
        # 3 more — bank rotates skill types so they look different
        await play_one("4", True)
        await play_one("5", True)
        await play_one("6", True)

        # End on the last activity — don't go back to home (user disliked that)
        stamp("end")
        await page.wait_for_timeout(400)

        await ctx.close()
        await b.close()

    webm = next(out_dir.glob("*.webm"))
    print(f"   gameplay webm: {webm.name}, checkpoints:")
    for k, v in checkpoints.items():
        print(f"      {k:<16}  +{v:6.2f}s")
    return webm, checkpoints


def synth_line(voice, text, out_wav):
    with wave.open(str(out_wav), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2)
        wav.setframerate(voice.config.sample_rate)
        voice.synthesize_wav(text, wav)
    with wave.open(str(out_wav), "rb") as w:
        return w.getnframes() / w.getframerate()


async def render_card(html_file, duration, out_mp4):
    png = BUILD / f"{html_file.stem}.png"
    if not png.exists():
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=2)
            p = await ctx.new_page()
            await p.goto("file://" + str(html_file))
            await p.wait_for_timeout(700)
            await p.screenshot(path=str(png))
            await b.close()
    n = max(1, int(round(duration * FPS)))
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(png),
        "-frames:v", str(n),
        "-vf", f"scale={W}:{H}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(out_mp4),
    ])


def webm_to_mp4(webm: Path, duration: float, out_mp4: Path):
    n = max(1, int(round(duration * FPS)))
    run([
        "ffmpeg", "-y", "-i", str(webm),
        "-frames:v", str(n),
        "-vf", f"scale={W}:{H}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-an", str(out_mp4),
    ])


def make_silence(seconds: float, sr: int, out_wav: Path):
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=mono:sample_rate={sr}",
        "-t", f"{seconds:.3f}",
        "-acodec", "pcm_s16le",
        str(out_wav),
    ])


def loudness(input_wav: Path, out_wav: Path):
    """Normalize loudness, gentle fade in/out, stop clipping.
    IMPORTANT: force output sample rate, because `loudnorm` upsamples to 192kHz
    internally and would corrupt our concat math otherwise."""
    run([
        "ffmpeg", "-y", "-i", str(input_wav),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.04",
        "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1",
        str(out_wav),
    ])


def concat_audio(parts: list, out_wav: Path):
    list_file = BUILD / "audio_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in parts))
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:a", "pcm_s16le",
        str(out_wav),
    ])


def concat_video(parts: list, out_mp4: Path):
    list_file = BUILD / "video_list.txt"
    list_file.write_text("\n".join(f"file '{p}'" for p in parts))
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an",
        str(out_mp4),
    ])


def mux(video: Path, audio: Path, out_mp4: Path):
    run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_mp4),
    ])


# ── narration script: paired with checkpoints in the gameplay timeline ──
# Each tuple: (target_checkpoint, text)
# We'll synth each line then place it at the checkpoint with leading silence.
NARR_INTRO_1 = "Meet Jane's Learning World."
NARR_INTRO_2 = "An adaptive learning tutor built just for one little kid."

TIMELINE = [
    ("welcome_in",     "She picks her world."),
    ("themes_hover",   "Unicorns, mermaids, dinosaurs, space, even Bluey."),
    ("q_1",            "Bloom asks fun questions made just for her."),
    ("a_1",            "Right answers earn sparkly stickers."),
    ("q_2",            "Reading, math, phonics, science, all in one place."),
    ("a_2",            "Two in a row."),
    ("q_3",            "And here comes the third."),
    ("celebrate",      "Three in a row, the whole screen throws a party."),
    ("q_4",            "Every question is fresh, generated just for her."),
    ("q_5",            "Never the same question twice."),
    ("q_6",            "The smarter she gets, the more challenging it grows."),
]

NARR_OUTRO_1 = "Powered by Claude. Voiced by LibriTTS."
NARR_OUTRO_2 = "Where learning feels like play."


async def main():
    voice = PiperVoice.load(str(ROOT / "voices" / "en_US-libritts_r-medium.onnx"))
    SR = voice.config.sample_rate

    step("1) record continuous gameplay")
    rec_dir = BUILD / "rec_continuous"
    webm, ck = await record_gameplay(rec_dir)
    gameplay_dur = ck["end"]
    print(f"   gameplay duration: {gameplay_dur:.2f}s")

    step("2) synth all narration lines")
    intro_wavs = []
    for i, t in enumerate([NARR_INTRO_1, NARR_INTRO_2]):
        wpath = BUILD / f"intro_{i}.wav"
        d = synth_line(voice, t, wpath)
        intro_wavs.append((wpath, d, t))
        print(f"   intro_{i:>2}  {d:5.2f}s  {t!r}")
    timed_lines = []
    for ck_name, text in TIMELINE:
        wpath = BUILD / f"line_{ck_name}.wav"
        d = synth_line(voice, text, wpath)
        timed_lines.append((ck_name, wpath, d, text))
        print(f"   {ck_name:<14}  {d:5.2f}s @ +{ck[ck_name]:5.2f}s  {text!r}")
    outro_wavs = []
    for i, t in enumerate([NARR_OUTRO_1, NARR_OUTRO_2]):
        wpath = BUILD / f"outro_{i}.wav"
        d = synth_line(voice, t, wpath)
        outro_wavs.append((wpath, d, t))
        print(f"   outro_{i:>2}  {d:5.2f}s  {t!r}")

    step("3) build narration audio for gameplay timeline")
    # Strategy: for each line, prepend silence to land at its checkpoint, then
    # mix down. Simpler: generate a single audio track equal to gameplay_dur
    # by concatenating silence + line + silence + line ... ensuring each line
    # starts at its checkpoint.
    last_end = 0.0
    parts = []
    for ck_name, wpath, d, _ in timed_lines:
        target_start = ck[ck_name]
        gap = max(0.0, target_start - last_end)
        if gap > 0.001:
            sil = BUILD / f"sil_{ck_name}.wav"
            make_silence(gap, SR, sil)
            parts.append(sil)
        norm = BUILD / f"norm_{ck_name}.wav"
        loudness(wpath, norm)
        parts.append(norm)
        last_end = target_start + d
    # Tail silence to fill out gameplay
    if gameplay_dur > last_end:
        tail = BUILD / "sil_tail.wav"
        make_silence(gameplay_dur - last_end, SR, tail)
        parts.append(tail)
    gameplay_narration = BUILD / "gameplay_narration.wav"
    concat_audio(parts, gameplay_narration)

    step("4) build intro audio (silence + line1 + silence + line2)")
    intro_dur = sum(d for _, d, _ in intro_wavs) + 0.6  # 0.3s padding before & between
    intro_parts = []
    sil_pre = BUILD / "intro_sil_pre.wav"; make_silence(0.3, SR, sil_pre); intro_parts.append(sil_pre)
    for i, (wpath, d, _) in enumerate(intro_wavs):
        nrm = BUILD / f"intro_norm_{i}.wav"; loudness(wpath, nrm); intro_parts.append(nrm)
        if i == 0:
            sil_mid = BUILD / "intro_sil_mid.wav"; make_silence(0.3, SR, sil_mid); intro_parts.append(sil_mid)
    intro_audio = BUILD / "intro_audio.wav"
    concat_audio(intro_parts, intro_audio)

    step("5) build outro audio")
    outro_parts = []
    sil_o_pre = BUILD / "outro_sil_pre.wav"; make_silence(0.4, SR, sil_o_pre); outro_parts.append(sil_o_pre)
    for i, (wpath, d, _) in enumerate(outro_wavs):
        nrm = BUILD / f"outro_norm_{i}.wav"; loudness(wpath, nrm); outro_parts.append(nrm)
        if i == 0:
            sil_o_mid = BUILD / "outro_sil_mid.wav"; make_silence(0.3, SR, sil_o_mid); outro_parts.append(sil_o_mid)
    sil_o_post = BUILD / "outro_sil_post.wav"; make_silence(0.6, SR, sil_o_post); outro_parts.append(sil_o_post)
    outro_audio = BUILD / "outro_audio.wav"
    concat_audio(outro_parts, outro_audio)

    step("6) determine card durations from audio")
    intro_dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(intro_audio)], capture_output=True, text=True).stdout.strip())
    outro_dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(outro_audio)], capture_output=True, text=True).stdout.strip())
    print(f"   intro card: {intro_dur:.2f}s   outro card: {outro_dur:.2f}s")

    step("7) render intro/outro card videos to those durations")
    intro_mp4 = BUILD / "intro.mp4"
    outro_mp4 = BUILD / "outro.mp4"
    await render_card(VID / "intro.html", intro_dur, intro_mp4)
    await render_card(VID / "outro.html", outro_dur, outro_mp4)

    step("8) gameplay webm → mp4 capped to gameplay duration")
    gameplay_mp4 = BUILD / "gameplay.mp4"
    webm_to_mp4(webm, gameplay_dur, gameplay_mp4)

    step("9) concat full audio: intro + gameplay narration + outro")
    full_audio = BUILD / "full_audio.wav"
    concat_audio([intro_audio, gameplay_narration, outro_audio], full_audio)

    step("10) concat full video")
    full_video = BUILD / "full_video.mp4"
    concat_video([intro_mp4, gameplay_mp4, outro_mp4], full_video)

    step("11) mix background music under narration")
    music = BUILD / "music_Wallpaper.mp3"
    final_audio = BUILD / "final_audio.wav"
    if music.exists():
        # Loop music to match audio length, then mix under narration at -22dB.
        # Sidechain compress so music ducks when narration is speaking.
        run([
            "ffmpeg", "-y",
            "-i", str(full_audio),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            (
                "[1:a]volume=0.20,aresample=22050[bgm];"  # music down to ~20%
                "[0:a]asplit=2[narr][narr2];"
                # use narration as sidechain ducker on music
                "[bgm][narr2]sidechaincompress=threshold=0.04:ratio=8:attack=10:release=400[ducked];"
                "[narr][ducked]amix=inputs=2:duration=first:dropout_transition=2,"
                "afade=t=in:st=0:d=0.6,"
                "afade=t=out:st=$(",  # filled below
            ),
            "-map", "[mixed]",
        ], **{}) if False else None  # disabled — switch to simpler robust approach below

        # Simpler robust mix: just mix at fixed levels with sidechain duck
        run([
            "ffmpeg", "-y",
            "-i", str(full_audio),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            (
                "[0:a]aresample=22050,volume=1.0[narr];"
                "[1:a]aresample=22050,volume=0.18[bgm];"
                "[narr][bgm]amix=inputs=2:duration=first:dropout_transition=0[mixed]"
            ),
            "-map", "[mixed]",
            "-acodec", "pcm_s16le", "-ar", "22050",
            str(final_audio),
        ])
    else:
        final_audio = full_audio

    step("12) mux")
    final = VID / "JaneOS_demo.mp4"
    mux(full_video, final_audio, final)
    print(f"\n✓ done → {final}")
    print(f"  size: {final.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    asyncio.run(main())
