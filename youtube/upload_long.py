"""Upload the 10-min Learning Fun: 1st Grade gameplay video."""
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).parent
TOKEN = ROOT / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
VIDEO = Path("/Users/matthewmacosko/Desktop/PROJECTS/JaneOS/video/JaneOS_long_demo.mp4")

TITLE = "Learning Fun: 1st Grade — FREE adaptive learning app for kids (10 min full gameplay)"

DESCRIPTION = """🌸 FREE kids learning — watch a full 10 minutes of Bloom, the adaptive 1st grade tutor I built for my daughter.

✨ Bloom is 100% FREE — no subscription, no ads, no in-app purchases, ever.
✨ Try it free: https://golf-dried-pierre-harry.trycloudflare.com
✨ Source code: https://github.com/nicedreamzapp/JaneOS

WHAT YOUR KID WILL LEARN IN BLOOM
📖 Reading — sight words like "the", "and", "you", "with", reading sentences
🔤 Phonics — short vowel sounds, beginning sounds, CVC words
👁️ Sight Words — high-frequency Dolch words for early readers
➕ Addition — within 10, then within 20
➖ Subtraction — within 10, then within 20
🔢 Place Value — tens and ones for 2-digit numbers
🔢 Counting — to 5, 10, 20, then 100
📚 Reading Sentences — fill-in-the-blank with sight words
🌿 Science — living/non-living, life cycles, weather, seasons, the senses
🌎 Social Studies — community helpers, polite words, where things happen
💖 Feelings (SEL) — recognizing emotions, kindness, calming strategies
✏️ Letter Tracing — handwriting practice on a touch-friendly canvas

WHO IT'S FOR
👨‍👩‍👧 Parents looking for a FREE kids learning app
🏠 Homeschool families needing a daily warm-up
🧑‍🏫 Kindergarten and 1st grade teachers
👧 Kids ages 5-7 working at K-2 level
👀 Anyone curious what an open-source AI tutor looks like

WHY PARENTS LOVE BLOOM
👍 Click-only — no microphone, no typing, totally safe for young kids
👍 No flashy slot-machine animations that overstimulate
👍 No data collection, no cloud accounts — runs entirely on your computer
👍 Adapts to your kid's actual level
👍 Free forever, MIT licensed open source

THE STORY
I'm a parent, not an EdTech founder. My 6-year-old needed a tutor that adapted to her, didn't bombard her with ads, and didn't cost $15/month. So I built Bloom over a weekend with Claude Code (Anthropic's pair-programming tool). My daughter named the tutor. We're sharing it because every kid deserves a friendly tutor that grows with them.

This is just the beginning. We're going to keep building.

ROADMAP
🌱 Auto-promotion to 2nd / 3rd grade
🌱 Spanish + bilingual mode
🌱 Multiple kid profiles per family
🌱 Weekly progress reports for parents
🌱 More themes (Disney, real planets, dinosaurs by era)
🌱 Drawing & coloring activities
🌱 Read-aloud picture book library
🌱 First-class iPad support

TECH (for the curious)
- Brain: Anthropic Claude Haiku 4.5 — same AI behind Claude.ai
- Voice: Piper TTS / LibriTTS R neural voice, runs 100% locally
- Backend: Python + aiohttp, single file
- Storage: SQLite per-skill mastery scores
- Public access: free Cloudflare Tunnel
- Background music: Kevin MacLeod (incompetech.com, CC BY 3.0)

Open source under MIT license. Star us on GitHub: https://github.com/nicedreamzapp/JaneOS

#FreeLearningApp #FreeKidsLearning #1stGradeApp #FirstGradeLearning #PhonicsApp #SightWordsApp #FreeMathForKids #HomeschoolApp #FreeKidsApp #LearningGames #KidsLearningGames #Homeschool #PreK #Kindergarten #EarlyLiteracy #ReadingForKids #MathForKids #LearningFun #FreeTutor #ToddlerLearning #FreeEducation #KidsApp #NoAds #OpenSource #Bloom
"""

TAGS = [
    "free learning app", "free kids learning", "1st grade",
    "first grade app", "phonics", "sight words", "kids reading",
    "free math", "homeschool app", "kindergarten",
    "early literacy", "reading for kids", "math for kids",
    "letter tracing", "kids learning games", "early reader",
    "preschool", "free tutor", "Bloom", "homeschool",
    "Learning Fun",
]


def get_creds():
    return Credentials.from_authorized_user_file(str(TOKEN), SCOPES)


def main():
    yt = build("youtube", "v3", credentials=get_creds())
    body = {
        "snippet": {
            "title": TITLE,
            "description": DESCRIPTION,
            "tags": TAGS,
            "categoryId": "27",
            "defaultLanguage": "en",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "madeForKids": False},
    }
    media = MediaFileUpload(str(VIDEO), mimetype="video/mp4", resumable=True, chunksize=2 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    print(f"uploading {VIDEO.stat().st_size/1024/1024:.1f} MB ...")
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")
    vid = response["id"]
    print(f"\n✓ uploaded: https://www.youtube.com/watch?v={vid}")


if __name__ == "__main__":
    main()
