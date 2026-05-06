"""Curated activity bank — instant fallback when LLM is slow/down.
Each activity has the same schema the frontend expects.
~80 activities across skills and difficulties, theme-agnostic (theme injected at serve time).
"""
import random

THEMES = ["unicorns", "mermaids", "dinos", "space", "cats", "horses", "bluey"]
THEME_EMOJI = {"unicorns": "🦄", "mermaids": "🧜‍♀️", "dinos": "🦕",
               "space": "🚀", "cats": "🐱", "horses": "🐴", "bluey": "🐶"}

BANK = []


def _add(skill, difficulty, say, screen_type, title, prompt, items, answer):
    BANK.append({
        "skill": skill, "difficulty": difficulty,
        "_template": {
            "say": say, "screen": {
                "type": screen_type, "title": title, "prompt": prompt,
                "items": items, "answer": answer,
            },
            "expects": "tap", "skill": skill, "difficulty": difficulty,
            "next_hint": "",
        },
    })


# ===== math_count (count emojis on screen) =====
for n in (2, 3, 4, 5):
    _add("math_count", 1,
         f"Count them and click the right number!",
         "image_word", "{EMOJI} " * n, "How many?",
         [str(x) for x in random.sample([1, 2, 3, 4, 5, 6], 4) if x != n][:3] + [str(n)],
         str(n))
for n in (6, 7, 8, 9):
    _add("math_count", 2,
         "Count carefully and click the right number!",
         "image_word", "{EMOJI} " * n, "How many?",
         sorted(set([str(n), str(n-1), str(n+1), str(n-2)]))[:4],
         str(n))

# ===== math_add (within 10) =====
for a in range(1, 6):
    for b in range(1, 6):
        if a + b > 10:
            continue
        ans = a + b
        wrongs = sorted({ans-1, ans+1, max(0, ans-2), ans+2} - {ans})[:3]
        items = sorted([str(ans)] + [str(x) for x in wrongs])
        _add("math_add", 1 if ans <= 5 else 2,
             f"What is {a} plus {b}? Click the answer!",
             "math", f"{a} + {b} = ?", "Click the answer!", items, str(ans))

# ===== math_sub (within 10) =====
for a in range(2, 11):
    for b in range(1, a):
        ans = a - b
        wrongs = sorted({ans-1, ans+1, max(0, ans-2), ans+2} - {ans})[:3]
        items = sorted([str(ans)] + [str(x) for x in wrongs])
        _add("math_sub", 1 if a <= 5 else 2,
             f"What is {a} minus {b}? Click the answer!",
             "math", f"{a} − {b} = ?", "Click the answer!", items, str(ans))

# ===== sight_words (Dolch-style, click the word the tutor SAYS) =====
SIGHT = [("the","th"), ("and","an"), ("you","yu"), ("was","ws"), ("for","fr"),
         ("are","ar"), ("see","ee"), ("can","ca"), ("come","cm"), ("here","hr"),
         ("look","lk"), ("play","pl"), ("said","sd"), ("with","wt"), ("they","th"),
         ("have","hv"), ("from","fm"), ("this","ti"), ("what","wh"), ("when","wn"),
         ("your","yr"), ("good","gd")]
for word, _ in SIGHT:
    distract = [w for w, _ in random.sample(SIGHT, 4) if w != word][:3]
    items = sorted([word] + distract)
    _add("sight_words", 1,
         f"Click the word that says \"{word}\".",
         "word", word.upper(), "Click the matching word!", items, word)

# ===== phonics_cvc (3-letter word recognition: click the word that starts with X sound) =====
CVC = [("c","cat","car","can","cup"), ("b","bat","bug","bed","bus"),
       ("d","dog","dad","den","dot"), ("f","fan","fox","fig","fun"),
       ("h","hat","hen","hip","hot"), ("m","mat","map","mom","mud"),
       ("p","pan","pen","pig","pot"), ("r","rat","red","rug","run"),
       ("s","sat","sip","sun","sad"), ("t","tap","ten","top","tub")]
for letter, *words in CVC:
    others = [w for ll, *ws in CVC if ll != letter for w in ws]
    decoys = random.sample(others, 3)
    items = sorted([words[0]] + decoys)
    _add("phonics_cvc", 1,
         f"Click the word that starts with the {letter.upper()} sound.",
         "phonics", letter.upper() + "...", "Click the word that starts with this sound!",
         items, words[0])

# ===== reading_fluency (which word fits the sentence?) =====
SENTENCES = [
    ("The ___ is in the sky.", "sun", ["sun", "rug", "cup", "bed"]),
    ("I can ___ fast.", "run", ["run", "sit", "eat", "bed"]),
    ("The cat is ___.", "big", ["big", "wet", "old", "red"]),
    ("My dog likes to ___.", "play", ["play", "read", "drive", "cook"]),
    ("She has a red ___.", "hat", ["hat", "leg", "ten", "sky"]),
    ("We ___ to school.", "go", ["go", "ate", "is", "had"]),
]
for sent, ans, items in SENTENCES:
    _add("reading_fluency", 2,
         f"Listen and click the word that fits.",
         "story", sent, "Which word makes sense?", items, ans)

# ===== math_place_value =====
PLACE = [(13, ["1 ten 3 ones", "3 tens 1 one", "13 tens", "30 ones"]),
         (24, ["2 tens 4 ones", "4 tens 2 ones", "24 tens", "20 ones"]),
         (37, ["3 tens 7 ones", "7 tens 3 ones", "37 tens", "73 ones"]),
         (45, ["4 tens 5 ones", "5 tens 4 ones", "45 tens", "54 ones"])]
for num, items in PLACE:
    _add("math_place_value", 3,
         f"What does {num} look like in tens and ones? Click the right one.",
         "math", str(num), "Tens and ones!", items, items[0])

# ===== science =====
SCIENCE = [
    ("Which one needs water to live?", "plant", ["plant", "rock", "spoon", "shoe"]),
    ("Which one is a baby cat called?", "kitten", ["kitten", "puppy", "calf", "chick"]),
    ("Which season is cold and snowy?", "winter", ["winter", "summer", "spring", "fall"]),
    ("What sense do we use to smell?", "nose", ["nose", "ears", "eyes", "feet"]),
    ("Which one is a butterfly's first stage?", "egg", ["egg", "wing", "flower", "rock"]),
    ("Which one lives in the ocean?", "fish", ["fish", "lion", "cow", "horse"]),
]
for q, ans, items in SCIENCE:
    _add("science", 2, q, "story", q, "Click the answer!", items, ans)

# ===== social =====
SOCIAL = [
    ("Who keeps your school safe?", "teacher", ["teacher", "doctor", "pilot", "chef"]),
    ("Where do you go to learn?", "school", ["school", "park", "store", "beach"]),
    ("What do you say to be polite?", "please", ["please", "yuck", "no way", "shh"]),
]
for q, ans, items in SOCIAL:
    _add("social", 1, q, "story", q, "Click the answer!", items, ans)

# ===== sel (feelings) =====
SEL = [
    ("If a friend falls down, what should we do?", "help", ["help", "laugh", "run", "ignore"]),
    ("How do you feel when you get a hug?", "happy", ["happy", "scared", "mad", "sleepy"]),
    ("What helps when you are mad?", "deep breaths", ["deep breaths", "yelling", "hitting", "running away"]),
]
for q, ans, items in SEL:
    _add("sel", 1, q, "story", q, "Click the answer!", items, ans)

# ===== writing_letter (trace it) =====
for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    BANK.append({
        "skill": "writing_letter", "difficulty": 1,
        "_template": {
            "say": f"Trace the letter {letter} with your finger!",
            "screen": {"type": "trace", "title": "", "prompt": f"Trace the {letter}!",
                       "answer": letter},
            "expects": "trace", "skill": "writing_letter", "difficulty": 1,
            "next_hint": "",
        },
    })


def serve(skill=None, difficulty=None, theme=None, exclude_titles=None):
    """Pick an activity from the bank, theme-injected. Theme defaults to random."""
    pool = BANK
    if skill:
        pool = [a for a in pool if a["skill"] == skill] or pool
    if difficulty:
        pool = [a for a in pool if a["difficulty"] == difficulty] or pool
    exclude_titles = exclude_titles or set()
    pool = [a for a in pool if a["_template"]["screen"].get("title") not in exclude_titles] or pool
    a = random.choice(pool)
    out = {**a["_template"]}
    out["screen"] = {**out["screen"]}
    theme = theme or random.choice(THEMES)
    out["screen"]["theme"] = theme
    # Inject theme emoji into title placeholder
    title = out["screen"].get("title", "")
    if "{EMOJI}" in title:
        out["screen"]["title"] = title.replace("{EMOJI}", THEME_EMOJI[theme]).strip()
    out["next_hint"] = ""
    return out


def stats():
    by = {}
    for a in BANK:
        by[a["skill"]] = by.get(a["skill"], 0) + 1
    return {"total": len(BANK), "by_skill": by}
