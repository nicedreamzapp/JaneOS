# Bloom — a free adaptive learning app for 1st graders

> **What it is:** a voice-guided AI tutor for kids ages 5–7 (kindergarten through 2nd grade). Free. Open source. Runs on your computer. No subscription, no ads, no in-app purchases — ever.

[![Watch the demo on YouTube](https://img.youtube.com/vi/AAPD_l9pUNE/maxresdefault.jpg)](https://www.youtube.com/watch?v=AAPD_l9pUNE)

> *Click the thumbnail above to watch the demo on YouTube*

🎮 **Live demo (try it on a phone or tablet right now):** https://golf-dried-pierre-harry.trycloudflare.com

---

## Why we built this

I (Matt, a parent) couldn't find a learning app for my 6-year-old daughter Jane that **(a)** actually adapted to her, **(b)** wasn't a slot machine of dopamine spikes designed to hook kids, and **(c)** didn't cost $15/month. So I built one with [Claude Code](https://claude.com/claude-code) over a weekend, my daughter named the tutor "Bloom", and we're putting it out for free because every kid deserves a friendly tutor that grows with them.

This is a **work in progress** and we're going to keep building. See the roadmap below.

## What your kid gets

She picks her favorite world — **🦄 unicorns, 🧜‍♀️ mermaids, 🦕 dinosaurs, 🚀 space, 🐱 cats, 🐴 horses, or 🐶 Bluey** — and Bloom (a warm, natural neural voice) leads her through bite-sized 60–90 second activities that adapt to her level.

### What Bloom teaches

| Subject | What Bloom covers |
|---|---|
| 📖 **Reading** | Sight words, sentence completion, comprehension |
| 🔤 **Phonics** | CVC words, beginning sounds, short vowels |
| ➕ **Math** | Counting to 10s, addition + subtraction within 10, place value |
| ✏️ **Writing** | Letter tracing on a touch canvas (handwriting practice) |
| 🌿 **Science** | Living/non-living, seasons, animal life cycles, the senses |
| 🌎 **Social Studies** | Community helpers, polite words, where things happen |
| 💖 **Social-Emotional** | Recognizing feelings, kindness, calming strategies |

### What makes it different

- 🌱 **Adaptive** — every right/wrong answer updates a per-skill mastery score. Weak skills get more practice. Difficulty climbs as your kid gets stronger and gently drops if they're struggling.
- 🌟 **Click-only safety** — no microphone, no typing, no scary AI chat. Your kid clicks the right answer. That's it.
- 🎉 **Real rewards** — sparkly stickers for right answers, full-screen confetti for 3-in-a-row streaks
- 🔇 **Works with sound off** — every answer shows a big visible green ✓ or red "Try again!" so audio is never required
- 🤫 **Private** — no cloud accounts, no login, no telemetry. SQLite on your machine.
- 💸 **Free forever** — MIT licensed. Run it locally on a Mac. We're not monetizing this.

## How it works (the simple version)

1. **The tutor's brain** is Anthropic's Claude — the same AI behind [Claude.ai](https://claude.ai) — generating fresh questions tailored to your kid every session.
2. **The tutor's voice** is the open-source [LibriTTS R](https://github.com/rhasspy/piper) neural voice running 100% locally via Piper TTS. No cloud TTS bills.
3. **The fallback brain** is a hand-curated bank of 158 activities so it stays instant even when the LLM is slow or offline.
4. **Storage** is a tiny SQLite file on your machine — Bloom remembers what your kid has mastered.

## Roadmap — where we're taking this

- 🌱 Auto-promotion to 2nd / 3rd grade as your kid grows
- 🌱 Spanish + bilingual mode
- 🌱 Multiple kid profiles per family
- 🌱 Weekly progress reports for parents
- 🌱 More themes (Bluey extended, Disney friends, real planets, dinosaurs by era)
- 🌱 Drawing & coloring activities
- 🌱 Read-aloud picture book library — Bloom reads stories
- 🌱 Goal setting from the parent dashboard
- 🌱 First-class iPad support
- 🌱 Optional ElevenLabs voice upgrade

📨 **Got a feature idea?** [Open an issue](https://github.com/nicedreamzapp/JaneOS/issues) and tell us what your kid would love.

## Run it yourself

You need a Mac (M1+ recommended) and ~5 minutes.

```bash
git clone https://github.com/nicedreamzapp/JaneOS.git
cd JaneOS
./setup.sh

# download the voice model (~78 MB)
mkdir -p voices && cd voices
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json
cd ..

./launch.sh
# now open http://localhost:9100 on any device on your network
```

Want it to autostart on every Mac boot? Drop `com.janeos.server.plist` in `~/Library/LaunchAgents/` and `launchctl load` it.

## Stack (for the curious)

| Layer | Tool |
|---|---|
| Brain | [Anthropic Claude Haiku 4.5](https://claude.ai) via the Claude Code CLI (Max plan, no per-token charges) |
| Voice | [Piper TTS](https://github.com/rhasspy/piper) — neural, runs 100% locally |
| Voice model | LibriTTS R (Apache 2.0 model, [CC BY 4.0 dataset from Google Research](https://www.openslr.org/141/)) |
| Backend | Python 3.12 + aiohttp, single-file server |
| Frontend | Vanilla HTML / CSS / JS, no build step |
| Storage | SQLite |
| Autostart | macOS `launchd` |
| Public access | Free [Cloudflare Tunnel](https://www.cloudflare.com/products/tunnel/) |
| Demo video | Playwright + ffmpeg, music by [Kevin MacLeod (incompetech.com)](https://incompetech.com/) under CC BY 3.0 |

## Tests

```bash
./.venv/bin/python sim.py           # API-level smoke test
./.venv/bin/python sim_full.py      # 7 themes × 5 activities, audio + feedback assertions
./.venv/bin/python sim_skills.py    # every skill type renders + grades correctly
./.venv/bin/python sim_audio.py     # TTS queue, visible feedback, auto-advance
```

## License

MIT for the code. Voice model and dataset under their own permissive licenses (Apache 2.0 + CC BY 4.0 — full credit to the [Piper](https://github.com/rhasspy/piper) team and [Google's LibriTTS team](https://www.openslr.org/141/)).

## Built with

Pair-programmed with [Claude Code](https://claude.com/claude-code). The kid named the tutor.

— Matt + Jane
