"""Upload JaneOS demo to YouTube. First run prompts OAuth in the browser."""
import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).parent
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # needed to update + delete videos
]
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN = ROOT / "token.json"

VIDEO = Path("/Users/matthewmacosko/Desktop/PROJECTS/JaneOS/video/JaneOS_demo.mp4")

TITLE = "Bloom — a FREE adaptive learning app for 1st graders | reading, phonics, math, sight words"

DESCRIPTION = """Bloom is a FREE adaptive learning app for first graders. I built it for my 6-year-old daughter Jane and I'm giving it away because every kid deserves a friendly tutor that adapts to them.

✨ FREE — no subscription, no ads, no in-app purchases, ever
✨ Try it: https://github.com/nicedreamzapp/JaneOS
✨ Live demo: https://golf-dried-pierre-harry.trycloudflare.com

WHAT YOUR KID GETS
Bloom is a warm voice-guided tutor that grows with your child. She picks the world she wants to play in — unicorns, mermaids, dinosaurs, space, cats, horses, or Bluey — and the tutor leads her through bite-sized 60-90 second activities. Reading. Phonics. CVC words. Sight words. Addition. Subtraction. Place value. Reading sentences. Science. Feelings (social-emotional learning). Even letter tracing for handwriting.

Every question is generated fresh by AI, so she never sees the same one twice. The difficulty automatically climbs as she masters skills, and gently drops if she's struggling. Right answers earn sparkly stickers. Three right in a row triggers a full-screen confetti party. Big visible feedback so it works whether the sound is on or off.

WHY PARENTS LOVE IT
👍 No typing, no microphone, no scary chat — just click the right answer, totally safe
👍 No flashy slot-machine animations that overstimulate kids
👍 No data collection, no cloud accounts — runs entirely on your computer
👍 Adapts to your kid's actual level instead of one-size-fits-all worksheets
👍 Built by a parent, for parents, with the same tools we used to build it

PERFECT FOR
- Parents looking for a free first grade learning app
- Homeschool families needing morning warmups in reading and math
- Kindergarten and 1st grade teachers who want a tool to differentiate
- Kids ages 5-7 working at K-2 level
- Quick learning sessions (10-15 minutes) that don't feel like a chore

ROADMAP — WHERE WE'RE TAKING IT
We're just getting started. What's coming:
🌱 Grade level auto-promotion (1st → 2nd → 3rd grade as your kid grows)
🌱 Spanish + bilingual mode
🌱 Multiple kid profiles per family
🌱 Weekly progress reports for parents
🌱 More themes (Bluey extended universe, Disney friends, dinosaurs by era, real planets)
🌱 Drawing/coloring activities and free-form play
🌱 A read-aloud library — Bloom reads picture books to your kid
🌱 Simple parent-controlled goal setting
🌱 iPad / iPhone first-class support
🌱 An optional ElevenLabs voice upgrade for even more natural narration

If you have feature requests, drop them as a GitHub issue: https://github.com/nicedreamzapp/JaneOS/issues

HOW IT WORKS UNDER THE HOOD (for the curious)
This is an open source project on GitHub anyone can run locally on their Mac. The tutor's brain is Anthropic Claude — the same model behind Claude.ai. The voice is the open-source Piper TTS LibriTTS R neural voice, running 100% locally so you don't pay per-word fees. There's no app store install, no account creation, no telemetry. Just clone the repo, run two scripts, and you're playing.

100% open source under the MIT license. Free forever.

BUILT WITH
- Claude Code (Anthropic) — pair-programmed the whole thing
- Claude Haiku 4.5 — generates fresh activities at runtime
- Piper TTS — neural voice synthesis, runs locally
- LibriTTS R voice — CC BY 4.0
- Python 3.12 + aiohttp + SQLite
- Playwright + ffmpeg for the demo
- Background music by Kevin MacLeod (incompetech.com, CC BY 3.0)

GET IT
GitHub: https://github.com/nicedreamzapp/JaneOS
Live demo: https://golf-dried-pierre-harry.trycloudflare.com

If you can't run it locally, just open the live demo on a tablet or laptop — your kid can play right now.

#FreeLearningApp #FirstGradeApp #1stGradeLearning #PhonicsApp #KidsReadingApp #HomeschoolApp #FreeKidsApp #SightWordsApp #FreeMathForKids #LearningGames #KidsLearningGames #Homeschool #PreK #Kindergarten #EarlyLiteracy #ReadingForKids #MathForKids #ToddlerLearning #FreeEducation #KidsApp #NoAds #OpenSource #Bloom #JanesLearningWorld
"""

TAGS = [
    # parent search terms
    "free learning app for kids", "first grade learning app", "1st grade app",
    "phonics app", "sight words app", "kids reading app", "free math app for kids",
    "homeschool app", "kindergarten learning app", "early literacy",
    "reading app for kids", "math for first graders", "letter tracing",
    "kids learning games", "free educational app", "no ads kids app",
    "early reader", "preschool learning", "free tutor app",
    # product
    "Bloom", "Bloom learning app", "Bloom tutor",
    # tech (some)
    "open source learning", "AI tutor for kids", "Claude AI",
]

CATEGORY_ID = "27"  # Education
PRIVACY = "public"


def get_creds():
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
            if creds and creds.valid:
                return creds
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN.write_text(creds.to_json())
                return creds
        except Exception as e:
            print(f"[oauth] saved token unusable: {e}")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent")
    TOKEN.write_text(creds.to_json())
    return creds


def main():
    if not VIDEO.exists():
        print(f"video not found: {VIDEO}")
        sys.exit(1)
    print(f"video: {VIDEO} ({VIDEO.stat().st_size/1024/1024:.2f} MB)")
    creds = get_creds()
    yt = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": TITLE,
            "description": DESCRIPTION,
            "tags": TAGS,
            "categoryId": CATEGORY_ID,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(VIDEO), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    print("uploading...")
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")
    vid = response["id"]
    url = f"https://www.youtube.com/watch?v={vid}"
    print(f"\n✓ uploaded: {url}")
    print(f"  privacy: {PRIVACY}")
    return url


if __name__ == "__main__":
    main()
