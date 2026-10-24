# 🤖 Attendance Bot
**Automated Attendance for Google Meet & Zoom**
Windows 11 · Local Machine · NVIDIA GPU Supported

---

## What's new in this version

**Dashboard (http://localhost:5000) is now the control panel** — no more editing JSON by hand:

| Tab | What it does |
|---|---|
| **Overview** | live status, current class, slides captured, alerts, live caption, attendance history |
| **Schedule** | paste a meeting link straight into any row of the timetable (press Enter — saves instantly, the bot reloads by itself); add / edit / delete classes; **Quick join** = join any meeting link right now |
| **Notes** | every Meet class's transcript, AI summary and slides PDF |
| **Settings** | your name / roll no / name spellings, "leave if fewer than N people", feature switches, AI provider + key |

**New features**
- **Lecture notes (always)** — every Meet class gets `notes/<Subject>/<date_time>/` with `transcript.md` and **`notes.pdf`** (+ `notes.html`). The PDF is built even for talk-only lectures and even with **no API key**:
  - **Cover:** stats, a colour timeline of how long each slide was on screen, and an **Exam radar** — moments where the teacher said exam / paper / quiz / important / remember / assignment / deadline (English and Urdu), plus the most repeated terms.
  - **At a glance:** a contact sheet of every slide (click to jump).
  - **One page per slide:** the screenshot, what was said while it was up, and any flagged moments.
  - **Full timed transcript** at the end.
- **Study chat** — open **Notes → Open notes + study chat** in the dashboard to view a class PDF beside a chatbot. Questions are answered from that class's saved notes/transcript using the configured AI provider; add a key in Settings to use it. The assistant says when the source material does not include an answer.
- **AI study notes (pick a provider in Dashboard → Settings → AI: Anthropic Claude, DeepSeek or Google Gemini; each key is stored locally in `.env`)** — the transcript is sent to the configured model and transformed into organized topic headings, explanations, formulas, examples, a summary, key terms, homework/deadlines, and a self-test. The PDF puts these study notes before any optional transcript appendix. If AI generation fails, the bot logs the provider error and marks the PDF accordingly; the original transcript is preserved separately.
- **PDF options (Dashboard → Settings)** — choose concise or detailed notes, A4 or US Letter paper, and whether to append the full transcript. The original full transcript is always saved separately as `transcript.md`.
- **Smart slide capture** — a new screenshot is taken when the slide changes; near-duplicate images already captured are skipped, and if the teacher reveals bullets one by one the **same slide's screenshot is updated** so you keep the complete version. While the screen is a video / whiteboard / scrolling document it takes a **snapshot every 30 s** (Settings). Each screenshot page includes a topic takeaway and teacher-explanation bullets from AI or the captured captions. Don't minimise the bot's Chrome window — minimised windows give blank screenshots. If a presentation isn't detected, set *Slide capture mode* to **always**.
- **Caption language** — Meet captions one language at a time. Default is Urdu (it also writes English words phonetically, which the detector understands). Choose **English** or *Keep Meet's own* in Settings, or per class in Schedule → Edit → *Captions language*. For an English YouTube lecture, choose **English**.
- **Video transcripts** — the bot records Google Meet's visible live captions; it does not fetch YouTube's own subtitle/transcript track. When a teacher plays a video, they must share the tab/screen with audio enabled and Meet captions must be on in a matching language. The bot warns in the log if captions have not appeared after 30 seconds.
- **Local video transcription** — Notes → Settings → Features enables the free `faster-whisper` base model, which listens to meeting playback through Windows WASAPI loopback, detects the spoken language, and adds speech missing from Meet captions to the lecture transcript. It runs locally on CPU (no account or API key); its model downloads once on first use. It needs the meeting audio unmuted and audible on the default Windows output. Loopback captures all audio rendered by that output device during class, not just Meet; it is kept locally. Meet captions still drive attendance detection, and duplicate recent caption text is filtered from the notes.
- **Transcript cleanup** — Meet remains the source of the transcript, so its live-caption errors cannot be recovered if Meet never recognized the words. With AI enabled, the bot now conservatively proofreads each captured caption segment, keeps the original `transcript.md`, and saves a separate `transcript_corrected.md`; uncertain corrections should be checked against the original/audio. Caption polling runs once per second and ignores common Meet/chat UI text.
- **"You were called" alert** — beeps + an always-on-top popup when your name or roll number is said, even outside roll call.
- **Chat fix** — the bot re-opens the chat panel before sending (caption settings used to hide it), retries a failed "Present" up to 5 times, only marks you present if it was really sent, and pops a loud alert if it gave up so you can type it yourself. A proof screenshot of each sent message goes to `screenshots/`.
- Console logging no longer crashes on Urdu characters; setup installs local `faster-whisper` (no PyTorch or CUDA required) and `tzdata`.

**Security notes:** the dashboard listens on this PC only (`127.0.0.1`). API keys are stored in the ignored local `.env` file, not `config/schedule.json`; never commit or share `.env`. To open the dashboard from your phone set `"dashboard": {"host": "0.0.0.0"}`, but only on a network you trust.

**Upgrading an existing install:** extract this zip over your project folder (replace files). Your `venv`, `profiles` (Google login) and `logs` folders are not in the zip, so they stay as they are. Then run `venv\Scripts\activate` and `pip install faster-whisper "tzdata"` once.

---

## Architecture Overview

```
attendance_bot/
├── bot.py                    ← Main entry point
├── watchdog.py               ← Crash recovery daemon
├── run.bat                   ← Windows run script
├── smart_setup.bat           ← One-time setup script
├── requirements.txt
│
├── config/
│   └── schedule.json         ← YOUR CLASS SCHEDULE (edit this)
│
├── core/
│   ├── config_loader.py      ← JSON config validation
│   ├── logger.py             ← Colored console + file logging
│   ├── scheduler.py          ← Class timing, consecutive class logic
│   └── session_manager.py    ← Join/monitor/leave orchestration
│
├── platforms/
│   ├── meet_handler.py       ← Google Meet automation (Playwright)
│   └── zoom_handler.py       ← Zoom web client automation
│
├── detection/
│   ├── attendance_detector.py ← Teacher phrase NLP (Urdu + English)
│   ├── burst_detector.py      ← 5+ "present" in 3s detection
│   └── whisper_asr.py         ← GPU-accelerated speech (fallback)
│
├── utils/
│   ├── caption_reader.py      ← Caption text buffer
│   ├── selectors.py           ← ALL DOM selectors (update here if UI changes)
│   ├── state_store.py         ← Runtime state (current class, status)
│   ├── attendance_logger.py   ← Excel + JSON history log
│   └── reconnect.py           ← Internet drop + waiting room handler
│
├── dashboard/
│   └── server.py              ← Flask dashboard at localhost:5000
│
├── logs/                      ← Auto-created
├── screenshots/               ← Auto-created (on errors)
└── profiles/chrome_profile/   ← Persistent Chrome login
```

---

## Quick Start

### Step 1 — Install
```bat
# Double-click setup.bat
# OR run in terminal:
setup.bat
```

### Step 2 — Configure Schedule
Edit `config/schedule.json`:
```json
{
  "student": {
    "name": "xyz",
    "roll_no": "xyz",
    "urdu_names": ["xyz"]
  },
  "classes": [
    {
      "id": "class_001",
      "day": "Saturday",
      "time": "06:56",
      "subject": "TEST CLASS 1",
      "link": "https://meet.google.com/pwu-ezkr-hsu",
      "platform": "meet",
      "duration": 120,
      "captions_available": true,
      "allowed_delay": 5,
      "_test": true
    }
  ]
}
```

### Step 3 — Configure API Keys (optional)
Copy `.env.example` to `.env` and add the key for the AI provider you use. The dashboard also saves keys to this local `.env` file.

```env
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
GEMINI_API_KEY=
```

`.env` is ignored by Git. Do not commit it; use `.env.example` as the safe template.

### Step 4 — Install ChromeDriver
Run `python install_chromedriver.py` in cmd or PowerShell. This installs the compatible Chrome driver for bot automation.

### Step 5 — First Run (Login Chrome)
```bat
venv\Scripts\activate
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch_persistent_context('profiles/chrome_profile', channel='chrome', headless=False); b.new_page().goto('https://accounts.google.com'); input('Login to Google, then press Enter...')"
```
> This saves your Google session so the bot doesn't need to log in every time.

### Step 6 — Test Run
```bat
python bot.py --test
```
Joins the first class marked `"_test": true` immediately.

### Step 7 — Production Run (Unattended)
```bat
# With crash recovery:
python watchdog.py

# Or direct:
run.bat
```

---

## How It Works

### Google Meet Flow
```
Schedule triggers class
    ↓
Wait 1 minute (join_delay)
    ↓
Launch Chrome (persistent profile = no re-login)
    ↓
Navigate to Meet link
    ↓
Disable mic + camera
    ↓
Click "Join Now" / "Ask to join"
    ↓
Handle waiting room (auto-wait up to 5 min)
    ↓
Enable Live Captions
    ↓
Monitor Loop (every 2 seconds):
    ├── Read captions from DOM
    ├── Read chat messages
    ├── Run Burst Detector (5+ "present" in 3s)
    ├── Run Attendance Detector (teacher phrases)
    └── Send "Present" or "Mic kharab hai" as needed
    ↓
End Condition:
    ├── Host ends meeting → leave
    ├── End time reached → leave
    └── Internet drop → reconnect + rejoin
```

### Attendance Detection Logic
```
Caption text analyzed every 2 seconds:

IF burst (5+ "present" in chat within 3s):
    → Check captions for name/roll
    → If found: send "Present"

IF teacher says attendance phrase:
    + Name/roll in captions:
        → send "Present"
    + Only first name, question context:
        → send "Mic kharab hai"

Teacher phrases detected (Urdu + English):
  - "main attendance mark kar raha hun"
  - "attendance lgwa lain"
  - "I am marking attendance"
  - "attendance call kar raha hun"
  ... (16 total patterns)
```

### Zoom Flow
```
Join via web browser (no app needed)
    ↓
Stay silent for full duration
    ↓
At end time: send "Present" in chat
    ↓
Leave meeting
```

### Consecutive Classes
```
Class A ends at 09:00
Class B starts at 09:05
    ↓
Bot auto-detects gap ≤ 15 min
    ↓
Leaves Class A → immediately joins Class B
```

---

## Configuration Reference

### global_settings
| Key | Default | Description |
|-----|---------|-------------|
| `join_delay_minutes` | 1 | Wait N min after class start before joining |
| `leave_tolerance_minutes` | 5 | Stay N min past end time before leaving |
| `reconnect_attempts` | 3 | Retry join if it fails |
| `reconnect_delay_seconds` | 30 | Wait between retries |
| `screenshot_on_error` | true | Save screenshot on crash |
| `stealth_mode` | true | Remove browser automation fingerprints |
| `browser_profile` | `profiles/chrome_profile` | Persistent login location |

### Per-class fields
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique class ID |
| `day` | string | Monday–Sunday |
| `time` | string | HH:MM (24hr, Pakistan Time) |
| `subject` | string | Display name |
| `link` | string | Full meeting URL |
| `platform` | string | `"meet"` or `"zoom"` |
| `duration` | int | Class length in minutes |
| `captions_available` | bool | Enable caption monitoring |
| `allowed_delay` | int | Extra minutes tolerance at end |
| `_test` | bool | If true, joins immediately in --test mode |

---

## Dashboard

Open **http://localhost:5000** while the bot is running.

Shows:
- Current class status (IDLE / IN_CLASS)
- Whether attendance was marked
- Full session history table
- Platform badges (Meet / Zoom)

---

## Updating DOM Selectors

If Google Meet updates its UI and captions stop working:

1. Open `utils/selectors.py`
2. Right-click the caption in Meet → Inspect Element
3. Find the new `jsname` or class
4. Update `MEET["caption_container"]`

No other files need to change.

---

## Local Speech Transcription

The optional feature uses the free, open-source `faster-whisper` package with the multilingual `base` model, CPU int8 inference, and automatic language detection. The package is installed by `smart_setup.bat`; the model files download from Hugging Face the first time the feature starts and are cached locally. No PyTorch, CUDA, account, or paid API key is needed.

On Windows it captures rendered sound via WASAPI loopback from the default Windows output device. This includes other audio played by that device during class, not only Meet. Meeting playback must remain unmuted and audible through that device. In the dashboard, open **Settings → Features** and enable **Locally transcribe meeting playback with Whisper**. If CPU usage is too high, disable it; the Google Meet caption reader continues to work independently.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot doesn't join | Check Chrome profile is logged into Google |
| Captions not reading | Update selectors in `utils/selectors.py` |
| "Join" button not found | Add `await asyncio.sleep(5)` before `_click_join()` |
| Zoom opens app instead of browser | Ensure link is `/j/` format, handler auto-converts |
| Local transcription has no audio | Ensure meeting audio is unmuted/audible on the Windows default output device; restart the class after changing the device |
| Whisper model or package unavailable | Run `venv\Scripts\activate` then `pip install faster-whisper`; check the bot log for model-download errors |
| Bot crashes repeatedly | Check `logs/watchdog.log` for error details |
| Wrong time zone | Change `PKT = ZoneInfo("Asia/Karachi")` in scheduler.py |

---

## Dependencies

```
playwright==1.44.0          Browser automation
schedule==1.2.1             Class scheduling
faster-whisper              Local multilingual speech recognition
flask==3.0.3                Dashboard web server
flask-socketio==5.3.6       Real-time dashboard updates
gspread==6.1.2              Google Sheets export (optional)
openpyxl==3.1.2             Excel attendance log
colorlog==6.8.2             Colored terminal output
rich==13.7.1                Pretty terminal tables
sounddevice==0.4.6          WASAPI loopback audio capture
```

---

## File Outputs

| File | Contents |
|------|----------|
| `logs/bot_YYYYMMDD.log` | Full debug log |
| `logs/attendance_history.json` | All session records |
| `logs/attendance.xlsx` | Excel attendance sheet |
| `logs/state.json` | Live bot state |
| `logs/watchdog.log` | Crash/restart history |
| `screenshots/*.png` | Error screenshots |
