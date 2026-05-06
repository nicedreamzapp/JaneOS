/* JaneOS — kid-friendly tutor app */

const $ = (id) => document.getElementById(id);
const cls = (el, c, on) => el.classList[on ? "add" : "remove"](c);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---- State ----
window.STATE = window.STATE || {};
const STATE = window.STATE;
Object.assign(STATE, {
  name: "Jane",
  tutorName: "Bloom",
  themes: ["unicorns","dinos","mermaids","bluey","space","cats","horses"],
  sessionId: null,
  theme: null,
  activitiesDone: 0,
  startedAt: 0,
  history: [],            // recent activities for the LLM
  current: null,          // current activity payload from /api/next
  rightStreak: 0,
  wrongStreak: 0,
  driftTimer: null,
  lastSpoken: "",
  recognition: null,
  voice: null,            // chosen TTS voice
});

// ---- Boot ----
(async function boot() {
  // Init voices early — Chrome populates async
  if ("speechSynthesis" in window) {
    speechSynthesis.onvoiceschanged = pickVoice;
    pickVoice();
  }

  try {
    const r = await fetch("/api/state");
    const s = await r.json();
    STATE.name = s.name || "Jane";
    STATE.tutorName = s.tutor_name || "Bloom";
    STATE.themes = s.themes || STATE.themes;
    $("welcome-name").textContent = STATE.name;
  } catch (e) {
    console.warn("state load failed", e);
  }

  // Theme buttons — prime audio on first click (browser autoplay policy)
  document.querySelectorAll(".theme-card").forEach(btn => {
    btn.addEventListener("click", () => { primeAudio(); onPickTheme(btn.dataset.theme); });
  });

  $("repeat-btn").addEventListener("click", repeatCurrent);
  $("next-btn").addEventListener("click", advance);
  $("break-btn").addEventListener("click", goHome);
  $("parent-btn").addEventListener("click", () => { window.location.href = "/parent"; });
})();

function pickVoice() {
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return;
  // Prefer the most natural-sounding voices first.
  // macOS "Premium"/"Enhanced" voices are neural and far better than the default.
  const order = [
    "Ava (Premium)", "Zoe (Premium)", "Allison (Premium)", "Samantha (Premium)",
    "Allison (Enhanced)", "Samantha (Enhanced)", "Ava (Enhanced)",
    "Google US English", "Microsoft Aria",
    "Ava", "Allison", "Samantha", "Karen", "Moira",
  ];
  for (const want of order) {
    const v = voices.find(x => x.name === want || x.name.startsWith(want));
    if (v) { STATE.voice = v; console.log("[tts] using voice:", v.name); return; }
  }
  STATE.voice = voices.find(v => v.lang && v.lang.startsWith("en")) || voices[0];
  if (STATE.voice) console.log("[tts] fallback voice:", STATE.voice.name);
}

// ---- Speak (server synthesizes Piper WAV, browser plays it) ----
// Works for ANY device — remote users hear audio in their own browser.
let _tts_audio = null;
let _tts_queue = [];
let _tts_playing = false;

function _playNextInQueue() {
  if (_tts_playing) return;
  const item = _tts_queue.shift();
  if (!item) return;
  _tts_playing = true;
  fetch("/api/say", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({text: item.text}),
  }).then(r => r.arrayBuffer()).then(buf => {
    const blob = new Blob([buf], {type: "audio/wav"});
    const url = URL.createObjectURL(blob);
    if (_tts_audio) { try { _tts_audio.pause(); } catch(_){} }
    _tts_audio = new Audio(url);
    _tts_audio.onended = () => {
      URL.revokeObjectURL(url);
      _tts_playing = false;
      _playNextInQueue();
    };
    _tts_audio.onerror = () => {
      URL.revokeObjectURL(url);
      _tts_playing = false;
      _playNextInQueue();
    };
    _tts_audio.play().catch(e => {
      console.warn("[tts] play failed (autoplay policy?)", e);
      _tts_playing = false;
      _playNextInQueue();
    });
    if (item.resolve) item.resolve();
  }).catch(e => {
    console.warn("[tts] fetch failed", e);
    _tts_playing = false;
    if (item.resolve) item.resolve();
    _playNextInQueue();
  });
}

function speak(text, opts = {}) {
  if (!text) return Promise.resolve();
  STATE.lastSpoken = text;
  return new Promise((resolve) => {
    _tts_queue.push({text: String(text), resolve});
    _playNextInQueue();
  });
}

function speakNow(text, opts = {}) {
  // Interrupt: stop current + clear queue
  _tts_queue = [];
  if (_tts_audio) { try { _tts_audio.pause(); } catch(_){} }
  _tts_playing = false;
  return speak(text, opts);
}

function primeAudio() {
  // Browser autoplay needs user gesture: kick off a silent fetch+play to "warm" the audio context
  if (STATE.audioPrimed) return;
  STATE.audioPrimed = true;
  // Just calling .play() inside a click handler is enough to grant audio permission
  try {
    const a = new Audio();
    a.volume = 0;
    a.play().catch(() => {});
  } catch(_) {}
}

// ---- Listen (STT) ----
function startListen() {
  return new Promise((resolve, reject) => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return reject(new Error("Speech recognition not supported"));
    if (STATE.recognition) {
      try { STATE.recognition.abort(); } catch (_) {}
    }
    const r = new SR();
    r.lang = "en-US";
    r.interimResults = false;
    r.maxAlternatives = 3;
    let got = false;
    r.onresult = (e) => {
      got = true;
      const alts = [];
      for (let i = 0; i < e.results[0].length; i++) alts.push(e.results[0][i].transcript);
      resolve(alts.join(" | "));
    };
    r.onerror = (e) => {
      if (!got) reject(new Error(e.error || "stt-error"));
    };
    r.onend = () => { if (!got) reject(new Error("no-speech")); };
    r.start();
    STATE.recognition = r;
  });
}

let listening = false;
async function toggleMic() {
  if (listening) {
    if (STATE.recognition) try { STATE.recognition.stop(); } catch(_){}
    return;
  }
  listening = true;
  cls($("mic-btn"), "listening", true);
  $("mic-btn").querySelector("span").textContent = "listening...";
  try {
    const heard = await startListen();
    onHeard(heard);
  } catch (e) {
    console.warn("stt err", e);
    flashFeedback("I didn't hear you, try again!", false);
  } finally {
    listening = false;
    cls($("mic-btn"), "listening", false);
    $("mic-btn").querySelector("span").textContent = "tap to talk";
  }
}

// ---- Theme pick → start session ----
async function onPickTheme(theme) {
  if (theme === "surprise") {
    theme = STATE.themes[Math.floor(Math.random() * STATE.themes.length)];
  }
  STATE.theme = theme;
  document.body.className = "";
  document.body.classList.add(`theme-${theme}`);

  // Start backend session
  try {
    const r = await fetch("/api/session/start", {method:"POST",headers:{"content-type":"application/json"},body: JSON.stringify({theme})});
    const j = await r.json();
    STATE.sessionId = j.session_id;
  } catch (e) { console.warn(e); }

  STATE.startedAt = Date.now();
  STATE.activitiesDone = 0;
  STATE.history = [];
  STATE.rightStreak = 0;
  STATE.wrongStreak = 0;

  // Switch screens
  cls($("welcome"), "active", false);
  cls($("lesson"), "active", true);

  // Show greeting in the bubble immediately (don't wait for TTS)
  $("said").textContent = `Hi ${STATE.name}! Let's play in the ${themePretty(theme)} world!`;
  $("content").innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';

  // Speak greeting (queue), then nextActivity will queue the prompt right after
  speak(`Hi ${STATE.name}! Let's play in the ${themePretty(theme)} world!`);
  await nextActivity();
}

// Convert UPPERCASE words to TitleCase so TTS doesn't spell them letter-by-letter
function ttsFriendly(text) {
  if (!text) return text;
  return String(text).replace(/\b[A-Z]{2,}\b/g, w => w[0] + w.slice(1).toLowerCase());
}

// "Say again" — cancel anything in flight and replay the CURRENT activity prompt
// (not whatever happened to be the last queued utterance). This is what the kid
// actually wants when she taps the repeat button.
function repeatCurrent() {
  const text = STATE.current?.say || STATE.lastSpoken || "";
  if (!text) return;
  speakNow(ttsFriendly(text));  // interrupt + replay
}

function themePretty(t) {
  return ({unicorns:"unicorn",mermaids:"mermaid",dinos:"dinosaur",space:"space",cats:"kitty cat",horses:"horse",bluey:"Bluey"})[t] || t;
}

// ---- Activity loop ----
async function fetchActivity() {
  try {
    const r = await fetch("/api/next", {
      method:"POST",
      headers:{"content-type":"application/json"},
      body: JSON.stringify({
        history: STATE.history.slice(-8),
        theme: STATE.theme,
        drift: false,
        frustration: STATE.wrongStreak >= 3,
      }),
    });
    return await r.json();
  } catch (e) {
    console.error(e);
    return {
      say: `Let's count, ${STATE.name}! Tap the right number.`,
      screen: {type:"image_word", title:"🦄 🦄 🦄", prompt:"Count them!", items:["2","3","4","5"], answer:"3", theme: STATE.theme},
      expects:"tap", skill:"math_count", difficulty:1,
    };
  }
}

function prefetchNext() {
  // Fire-and-forget so the next activity is ready when she finishes the current one
  STATE.prefetched = fetchActivity();
}

async function nextActivity() {
  cls($("next-btn"), "hidden", true);
  resetDrift();

  // Use prefetched if available — instant
  let payload;
  if (STATE.prefetched) {
    try { payload = await STATE.prefetched; } catch (_) {}
    STATE.prefetched = null;
  }
  if (!payload) {
    showLoading();
    payload = await fetchActivity();
  }
  STATE.current = payload;
  renderActivity(payload);
  prefetchNext();
  // Speak in parallel with rendering. Queue model means greeting/praise still play.
  speak(ttsFriendly(payload.say || "Here we go!"));
  startDriftTimer();
}

function showLoading() {
  $("said").textContent = "...";
  const c = $("content");
  c.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
}

function _kidify(text) {
  // Normalize copy: kid uses a mouse, so "tap" → "click" everywhere visible
  if (typeof text !== "string") return text;
  return text
    .replace(/\bTap\b/g, "Click")
    .replace(/\btap\b/g, "click")
    .replace(/\bTAP\b/g, "CLICK");
}

function renderActivity(p) {
  if (p) p.say = _kidify(p.say);
  if (p?.screen) {
    p.screen.title = _kidify(p.screen.title);
    p.screen.prompt = _kidify(p.screen.prompt);
  }
  $("said").textContent = p.say || "";
  // Bubble itself is tappable to repeat
  const bubble = document.querySelector(".bubble");
  if (bubble && !bubble.__wired) {
    bubble.__wired = true;
    bubble.style.cursor = "pointer";
    bubble.addEventListener("click", repeatCurrent);
    bubble.title = "Click to hear again";
  }
  const c = $("content");
  c.innerHTML = "";
  const s = p.screen || {};
  const theme = s.theme || STATE.theme;
  if (theme && theme !== STATE.theme) {
    document.body.className = "";
    document.body.classList.add(`theme-${theme}`);
    STATE.theme = theme;
  }

  if (s.title) {
    const h = document.createElement("h2");
    h.className = "title-big";
    // Counting activities get the framed "card" so kid knows what to count
    if (s.type === "image_word") h.classList.add("count-card");
    h.textContent = s.title;
    c.appendChild(h);
  }
  if (s.prompt) {
    const pr = document.createElement("p");
    pr.className = "prompt-line";
    pr.textContent = s.prompt;
    c.appendChild(pr);
  }
  if (s.scene) {
    const se = document.createElement("div");
    se.className = "scene-emojis";
    se.textContent = s.scene;
    c.appendChild(se);
  }

  if (s.type === "trace") {
    const box = document.createElement("div");
    box.className = "trace-box";
    box.innerHTML = `<div class="ghost">${s.answer || "A"}</div><canvas></canvas>`;
    c.appendChild(box);
    setupTrace(box);
  }

  if (Array.isArray(s.items) && s.items.length) {
    const opts = document.createElement("div");
    opts.className = "options";
    s.items.forEach(item => {
      const b = document.createElement("button");
      // Tolerate plain strings OR objects like {label, word, emoji, image}
      const label = (typeof item === "string")
        ? item
        : (item.label || item.word || item.text || item.emoji || item.value || JSON.stringify(item));
      const value = (typeof item === "string")
        ? item
        : (item.word || item.value || item.label || label);
      b.textContent = label;
      b.addEventListener("click", () => onTap(value, b));
      opts.appendChild(b);
    });
    c.appendChild(opts);
  }

  // Safety net: if backend forgot tap items for an unsupported "speech" type, give her something to tap
  if (!Array.isArray(s.items) && p.expects !== "trace") {
    const opts = document.createElement("div");
    opts.className = "options";
    const tryAgain = document.createElement("button");
    tryAgain.textContent = "next";
    tryAgain.addEventListener("click", () => { grade("skip", true); });
    opts.appendChild(tryAgain);
    c.appendChild(opts);
  }
}

function setupTrace(box) {
  const canvas = box.querySelector("canvas");
  const rect = box.getBoundingClientRect();
  canvas.width = rect.width; canvas.height = rect.height;
  const ctx = canvas.getContext("2d");
  ctx.lineWidth = 14; ctx.lineCap = "round"; ctx.strokeStyle = "#ff3aa1";
  let drawing = false;
  const pos = (e) => {
    const r = canvas.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return {x: t.clientX - r.left, y: t.clientY - r.top};
  };
  const start = (e) => { drawing = true; const p = pos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); e.preventDefault(); };
  const move = (e) => { if (!drawing) return; const p = pos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); e.preventDefault(); };
  const end = () => { drawing = false; };
  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  canvas.addEventListener("mouseup", end);
  canvas.addEventListener("touchstart", start);
  canvas.addEventListener("touchmove", move);
  canvas.addEventListener("touchend", end);
  // Trace counts as success on first stroke completion (kids practice, not perfection)
  canvas.addEventListener("touchend", () => onTraceDone());
  canvas.addEventListener("mouseup", () => onTraceDone());
}
function onTraceDone() {
  // give a beat then advance
  setTimeout(() => grade("traced", true), 600);
}

async function onTap(value, btn) {
  resetDrift();
  const expected = String(STATE.current?.screen?.answer ?? "").trim();
  // Forgiving grading: trim, lowercase, also accept "5" === "5 stars"-style answers
  const v = String(value).trim().toLowerCase();
  const e = expected.toLowerCase();
  const numV = (v.match(/-?\d+/) || [])[0];
  const numE = (e.match(/-?\d+/) || [])[0];
  const correct = v === e || (numV && numV === numE) || v.startsWith(e) || e.startsWith(v);
  if (correct) btn.classList.add("right");
  else btn.classList.add("wrong");
  await sleep(450);
  grade(value, correct);
}

async function onHeard(text) {
  resetDrift();
  const expected = String(STATE.current?.screen?.answer ?? "").trim();
  // Send to backend for fuzzy grading
  let correct = false, feedback = "";
  try {
    const r = await fetch("/api/grade", {
      method:"POST",
      headers:{"content-type":"application/json"},
      body: JSON.stringify({expected, got: text, skill: STATE.current?.skill}),
    });
    const j = await r.json();
    correct = !!j.correct;
    feedback = j.feedback || "";
  } catch (e) { correct = false; }
  grade(text, correct, feedback);
}

async function grade(got, correct, feedback) {
  // Persist
  try {
    await fetch("/api/attempt", {
      method:"POST",
      headers:{"content-type":"application/json"},
      body: JSON.stringify({
        session_id: STATE.sessionId,
        skill: STATE.current?.skill,
        difficulty: STATE.current?.difficulty,
        prompt: STATE.current?.screen?.title || STATE.current?.screen?.prompt || "",
        expected: STATE.current?.screen?.answer || "",
        got,
        correct,
        latency_ms: 0,
        theme: STATE.theme,
      }),
    });
  } catch (e) { console.warn(e); }

  STATE.history.push({
    skill: STATE.current?.skill,
    difficulty: STATE.current?.difficulty,
    correct,
    prompt: STATE.current?.screen?.title || "",
  });

  // VISIBLE feedback (no-audio path) — flash a card overlay and update bubble
  const phrase = correct ? pickPraise(feedback) : pickGentleTry(feedback, STATE.current?.screen?.answer);
  $("said").textContent = phrase;
  flashFeedbackCard(correct, correct ? "✓" : "Try again!");

  if (correct) {
    STATE.rightStreak++; STATE.wrongStreak = 0;
    addSticker();
    speak(phrase);
    if (STATE.rightStreak >= 3) {
      bigCelebrate();
      STATE.rightStreak = 0;
    }
  } else {
    STATE.wrongStreak++; STATE.rightStreak = 0;
    speak(phrase);
  }
  STATE.activitiesDone++;
  // Wait long enough for the kid to read the feedback, then advance.
  await sleep(correct ? 1100 : 1700);
  nextActivity();
}

function flashFeedbackCard(correct, label) {
  const el = document.createElement("div");
  el.className = "fb-flash " + (correct ? "fb-yes" : "fb-no");
  el.textContent = label;
  document.body.appendChild(el);
  // Auto-clean
  setTimeout(() => el.remove(), 1400);
}

function pickPraise(extra) {
  const p = ["Yes! Nice work, " + STATE.name + "!", "You got it!", "Awesome!", "Boom! Right!", "Look at you go!", "Smart cookie!"];
  return (extra ? extra + " " : "") + p[Math.floor(Math.random()*p.length)];
}
function pickGentleTry(extra, answer) {
  const p = ["Almost! Let's try once more.", "So close! Let's try again.", "Good try! Here's a hint."];
  const base = (extra ? extra + " " : "") + p[Math.floor(Math.random()*p.length)];
  return answer ? `${base} The answer is ${answer}.` : base;
}

function addSticker() {
  const stickers = ["⭐","🌈","🎉","💖","🦋","🌟","🍭","🎈","🪄","✨","🍩","🌺"];
  const s = document.createElement("span");
  s.className = "sticker-pop";
  s.textContent = stickers[Math.floor(Math.random()*stickers.length)];
  $("stickers").appendChild(s);
  // keep only last 8
  while ($("stickers").children.length > 8) $("stickers").removeChild($("stickers").firstChild);
}

function bigCelebrate() {
  STATE.celebrateCount = (STATE.celebrateCount || 0) + 1;  // observable for tests
  const phrases = ["AMAZING!","WOOHOO!","SUPERSTAR!","INCREDIBLE!","YOU ROCK!"];
  $("celebrate-text").textContent = phrases[Math.floor(Math.random()*phrases.length)];
  cls($("celebrate"), "show", true);
  cls($("celebrate"), "hidden", false);
  fireConfetti();
  setTimeout(() => {
    cls($("celebrate"), "show", false);
    cls($("celebrate"), "hidden", true);
  }, 1800);
}

// ---- Confetti ----
function fireConfetti() {
  const canvas = $("confetti");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width = window.innerWidth;
  const H = canvas.height = window.innerHeight;
  const colors = ["#ff3aa1","#6b4eff","#00b894","#ffd166","#4ea8ff","#ff8a4d"];
  const pieces = [];
  for (let i = 0; i < 140; i++) {
    pieces.push({
      x: W/2 + (Math.random()-0.5)*200,
      y: H/2 + (Math.random()-0.5)*100,
      vx: (Math.random()-0.5) * 18,
      vy: -Math.random() * 16 - 6,
      g: 0.5 + Math.random()*0.4,
      r: Math.random()*Math.PI,
      vr: (Math.random()-0.5)*0.3,
      size: 8 + Math.random()*8,
      color: colors[Math.floor(Math.random()*colors.length)],
    });
  }
  let t0 = performance.now();
  function frame(t) {
    const dt = Math.min(40, t - t0); t0 = t;
    ctx.clearRect(0,0,W,H);
    let alive = 0;
    for (const p of pieces) {
      p.vy += p.g;
      p.x += p.vx; p.y += p.vy; p.r += p.vr;
      if (p.y < H + 40) alive++;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.r);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size/2, -p.size/2, p.size, p.size*0.5);
      ctx.restore();
    }
    if (alive > 0) requestAnimationFrame(frame);
    else ctx.clearRect(0,0,W,H);
  }
  requestAnimationFrame(frame);
}

// (Floating theme creatures removed — they confused counting activities.)

function flashFeedback(msg, ok) {
  $("said").textContent = msg;
}

// ---- Drift detection ----
function startDriftTimer() {
  resetDrift();
  STATE.driftTimer = setTimeout(async () => {
    // Tell the API we're drifting → it'll pick something snappier
    await speak("Hey " + STATE.name + ", still with me? Let's try something silly!");
    nextActivity();
  }, 14000);
}
function resetDrift() {
  if (STATE.driftTimer) { clearTimeout(STATE.driftTimer); STATE.driftTimer = null; }
}

// ---- Break / Home ----
async function goHome() {
  resetDrift();
  speechSynthesis.cancel();
  if (STATE.sessionId) {
    const seconds = Math.round((Date.now() - STATE.startedAt) / 1000);
    fetch("/api/session/end", {
      method:"POST",
      headers:{"content-type":"application/json"},
      body: JSON.stringify({session_id: STATE.sessionId, seconds, activities: STATE.activitiesDone}),
    }).catch(()=>{});
  }
  STATE.sessionId = null;
  STATE.prefetched = null;
  cls($("lesson"), "active", false);
  cls($("welcome"), "active", true);
  document.body.className = "";
}

function advance() { nextActivity(); }
