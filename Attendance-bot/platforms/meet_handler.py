import asyncio
import queue
import re
import time as _time
from collections import deque
from pathlib import Path
from typing import List, Dict, Optional

from playwright.async_api import async_playwright, BrowserContext
from core.logger import setup_logger
from detection.attendance_detector import AttendanceDetector
from detection.whisper_asr import WhisperRecognizer
from core import config_store
from utils.alerts import CalledAlert
from utils.lang_utils import normalize_urdu
from utils.slide_capture import SlideCapture
from utils.selectors import MEET
from utils import ai_notes

logger = setup_logger("MeetHandler")

_CAPTION_UI = re.compile(
    r"no chat messages yet|format_size|open caption settings|font size|font colour|"
    r"returning to home screen|\b\d+\s+seconds?\s+left\b|"
    r"\blanguage\s*:\s*english\b",
    re.IGNORECASE,
)
def _urdu_words(*words) -> str:
    """Alternation of Urdu-script words, folded the same way captions are folded."""
    return "|".join(sorted({re.escape(normalize_urdu(w)) for w in words}, key=len, reverse=True))


def _word(alternatives: str) -> str:
    return rf"(?<!\w)(?:{alternatives})(?!\w)"


def _norm(text) -> str:
    """Case-fold + fold Urdu spelling variants so cue words match however the captions spell them."""
    return normalize_urdu(text).casefold()


# Question words in English, Roman Urdu, Urdu script and Devanagari (Whisper sometimes writes
# Urdu speech in Devanagari).
_ROMAN_WH = ("kya|kia|kiya|kyun|kyon|kyu|kaise|kaisay|kese|kesay|kaisa|kaisi|kesa|kesi|kab|kahan|"
             "kahaan|kaun|kon|konsa|kaunsa|kitna|kitni|kitne|kis")
_URDU_WH = _urdu_words("کیا", "کیوں", "کیسے", "کیسا", "کیسی", "کب", "کہاں", "کون", "کونسا",
                       "کونسی", "کس", "کتنا", "کتنی", "کتنے", "کدھر")
_DEVA_WH = "क्या|क्यों|कैसे|कैसा|कैसी|कब|कहाँ|कहां|कौन|किस|कितना|कितनी|कितने"
# Prompts to answer / explain.
_ROMAN_ASK = ("batao|bataiye|bataye|bataen|batayen|batado|samjhao|samjhaiye|samjhain|samjhen|"
              "jawab|jawaab|bolo|boliye|bolen")
_URDU_ASK = _urdu_words("جواب", "بتائیں", "بتائیے", "بتایئے", "بتاؤ", "بتاو", "بتادیں", "سمجھائیں",
                        "سمجھائیے", "سمجھاؤ", "سمجھاو", "بولیں", "بولیے", "بولو", "وضاحت")
_DEVA_ASK = "बताइए|बताओ|बताएं|समझाइए|समझाओ|जवाब|बोलिए"

_QUESTION_CUE = re.compile(
    r"[?؟]|"
    + _word(r"what|why|how|when|where|which|who|whose|whom|" + _ROMAN_WH + "|" + _URDU_WH + "|" + _DEVA_WH)
    + r"|\b(?:can|could|would|should|will)\s+you\b",
    re.IGNORECASE,
)
_ANSWER_PROMPT = re.compile(
    _word(r"answer|respond|explain|tell us|your thoughts|" + _ROMAN_ASK + "|" + _URDU_ASK + "|" + _DEVA_ASK),
    re.IGNORECASE,
)
_MIC_QUESTION_PROMPT = re.compile(
    r"\b(?:explain|define|summarize|summarise|tell me|what is|how does|"
    r"why does|compare|describe)\b|(?:سمجھائیں|بتائیں|وضاحت)",
    re.IGNORECASE,
)


_WH_WORD = re.compile(
    _word(r"what|why|how|when|where|which|who|define|" + _ROMAN_WH + "|" + _URDU_WH + "|" + _DEVA_WH),
    re.IGNORECASE,
)
# "can you ..." in English / Roman Urdu / Urdu
_CALL_ON = re.compile(
    r"\b(?:can|could|would|will)\s+you\b|" + _word(r"sakt[eai]|" + _urdu_words("سکتے", "سکتا", "سکتی")),
    re.IGNORECASE,
)

_CHAT_TIME = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?$", re.I)
_CHAT_UI = {"hover over a message to pin it", "keep", "pin message", "unpin message", "unpin",
            "pinned", "you", "copy", "reply", "more options", "delete"}
_SPLIT = re.compile(r"[\s,.;:!?\u061f\u06d4\"'()\[\]{}\-]+")
# Words that carry no topic: ignored when judging "is this the same question again?" and
# "does this sentence contain a real question, or just 'Saad, you answer'?"
_FILLER = frozenset(
    "you me us please now sir madam ji aap ap tum tu mujhe mujhay mjhe zara ab toh to aur and the a an "
    "is are was were of it this that in on at for with what why how when where which who define do does "
    "can could would will tell explain answer respond say give batao bataiye bataen kya kia kaise kese "
    "hai hain ho ka ki ke ko se me mein "
    "آپ مجھے اب تو اور ہے ہیں میں کو کی کا کے سے کیا کیسے کیوں "
    "मुझे आप अब तो और है हैं में को की का के से क्या कैसे क्यों बताओ बताइए समझाओ".split()
)


def _tokens(text) -> list:
    return [t for t in _SPLIT.split(str(text or "")) if t]


def _parse_chat_messages(text) -> list:
    """Meet's chat panel is ONE block of text: [name] / time / message / UI words ("keep", "Pin
    message") ... Return only OTHER people's messages. My own messages (a group with no name line
    before its timestamp) - including every answer this bot typed - are skipped, otherwise the bot
    would read its own replies as new questions and answer itself forever."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    messages, sender, pending = [], None, None
    for index, line in enumerate(lines):
        low = line.lower()
        if _CHAT_TIME.match(line):
            sender, pending = pending, None          # a name right before the time => someone else
            continue
        if low in _CHAT_UI or len(low) <= 1:
            continue
        next_is_time = index + 1 < len(lines) and bool(_CHAT_TIME.match(lines[index + 1]))
        after_ui = index == 0 or lines[index - 1].lower() in _CHAT_UI or bool(_CHAT_TIME.match(lines[index - 1]))
        if next_is_time and after_ui and len(line) <= 40 and len(line.split()) <= 4:
            pending = line                            # sender name line
            continue
        if sender:
            messages.append(low)
    return messages



# Teacher turning to ANOTHER student: a roll number, or a name used as "Ali, can you ..." / "..., Ali?"
_ANY_ROLL = re.compile(r"(?<!\w)\d{2}\s*k\s*-?\s*\d{4}(?!\w)", re.IGNORECASE)
_VOCATIVE = re.compile(
    r"^\s*([A-Za-z]{2,15}|[\u0600-\u06ff]{2,15})\s*[,\u060c]\s*"
    r"(?:can|could|will|would|what|why|how|when|where|which|who|you|please|tell|explain|answer|"
    r"batao|kya|aap|tum)\b", re.IGNORECASE)
_TRAILING_NAME = re.compile(r",\s*([A-Z][a-z]{2,14})\s*[?.!]?\s*$")
_NOT_A_NAME = {
    "so", "okay", "ok", "now", "well", "yes", "no", "right", "alright", "and", "but", "then", "also",
    "next", "see", "look", "first", "second", "third", "for", "if", "as", "because", "actually",
    "basically", "suppose", "let", "listen", "tell", "please", "hello", "hi", "sir", "guys",
    "students", "class", "everyone", "everybody", "anyone", "anybody", "sorry", "thanks", "thank",
}


def _sentences(text) -> list:
    return [p.strip() for p in re.split(r"(?<=[.?!\u061f\u06d4\u0964])\s+", str(text or "").strip()) if p.strip()]


def _parse_caption_blocks(raw) -> list:
    blocks = []
    for value in raw or []:
        lines = [line.strip() for line in str(value).splitlines() if line.strip()]
        if not lines:
            continue
        text = " ".join(lines[1:] if len(lines) >= 2 else lines)
        speaker = lines[0] if len(lines) >= 2 else ""
        if not text or _CAPTION_UI.search(" ".join(lines)):
            continue
        blocks.append((speaker, text))
    return blocks


class MeetHandler:
    def __init__(self, cls: Dict, config: Dict):
        self.cls      = cls
        self.config   = config
        self.settings = config["global_settings"]
        self.student  = config["student"]
        self.link     = cls.get("link", "").strip()
        self.playwright  = None
        self.context: Optional[BrowserContext] = None
        self.page        = None
        self.detector    = AttendanceDetector(config)
        self.captions: deque = deque(maxlen=50)
        self._question_caption_texts = {}
        self._seen_chat_message_set = set()
        self._pending_live_question = ""
        self._pending_live_question_at = 0.0
        self._pending_name_at = 0.0
        self._last_queued_question = ""
        self._question_answer_task = None
        self._missing_question_key_logged = False
        self._recent_sentences = deque(maxlen=6)
        self._sent_chat_norms = set()
        self._attendance_mode_until = 0.0
        self._attendance_marked = False
        self._present_request = None
        self._last_present_sent = 0.0
        self._answer_block_until = 0.0
        self._recent_answered = deque(maxlen=8)
        self._ai_check_task = None
        self._ai_checked = set()
        self._ai_window_start = 0.0
        self._ai_calls = 0
        self._chat_opened = False
        self.features    = config_store.get_features(config)
        self.recorder    = None            # NotesRecorder (attached by SessionManager)
        self.slides      = None            # SlideCapture
        self.alert       = CalledAlert(config)
        self._pending_present  = False     # "Present" detected but not yet sent
        self._present_tries    = 0
        self._last_present_try = 0.0
        self._caption_check_started = 0.0
        self._caption_seen = False
        self._caption_warning_logged = False
        self.whisper = None
        self._whisper_texts: queue.Queue = queue.Queue()
        self._whisper_speech: queue.Queue = queue.Queue()
        self._last_chat_log = None
        self._end_checked_at = 0.0
        self._end_hits = 0
        self._alone_since = 0.0
        self._was_in_call = False
        self._weak_hits = 0
        self.end_reason = ""
        code = re.search(r"meet\.google\.com/(?:lookup/)?([a-z]{3}-[a-z]{4}-[a-z]{3})", self.link or "", re.I)
        self._meeting_code = code.group(1).lower() if code else ""

    def attach_recorder(self, rec):
        """Hook up lecture notes + slide capture for this session."""
        self.recorder = rec
        ft = self.features
        if rec is not None and rec.enabled and ft.get("slides") and ft.get("slide_mode") != "off":
            self.slides = SlideCapture(rec.slides_dir, ft.get("slide_mode", "auto"),
                                       ft.get("slide_interval", 4), on_slide=rec.add_slide,
                                       keyframe_secs=ft.get("keyframe_interval", 30))

    async def join(self):
        # Guard: skip if no link
        if not self.link:
            raise RuntimeError("No link provided for this class — skipping.")

        logger.info(f"[Meet] Joining: {self.link}")
        if self.whisper is not None:                 # a failed earlier attempt may still hold the audio
            self.stop_audio()

        profile = Path(self.settings.get("browser_profile", "profiles/bot_profile")).absolute()
        profile.mkdir(parents=True, exist_ok=True)

        # Close any existing session first
        if self.playwright:
            try:
                await self.context.close()
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
            self.context    = None
            self.page       = None

        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--use-fake-ui-for-media-stream",
                "--disable-notifications",
                "--start-maximized",
            ],
            ignore_default_args=["--enable-automation"],
            no_viewport=True,
        )

        self.page = await self.context.new_page()
        await self.page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

        # Close any extra tabs that open (popups, redirects etc)
        async def close_extra_pages(page):
            if page != self.page:
                await page.close()
        self.context.on("page", close_extra_pages)

        await self.page.goto(self.link, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # Check if Google is asking for sign-in — auto sign-in using stored credentials
        if "accounts.google.com" in self.page.url:
            logger.warning("[Meet] Session expired — auto signing in...")
            await self._auto_sign_in()
            await self.page.goto(self.link, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

        await self.page.locator("body").click()
        await asyncio.sleep(0.5)

        await self._mute_mic(force=True)
        await self._mute_cam(force=True)

        await self._click_join()

        await asyncio.sleep(2)
        await self._open_chat()
        await self._enable_captions()
        try:
            await self._ensure_chat_visible()   # caption settings hide the chat panel
        except Exception:
            pass

        logger.info("[Meet] Joined successfully with mic/cam OFF.")
        if self.features.get("whisper_transcription", True):
            self.whisper = WhisperRecognizer(
                on_transcript=self._whisper_texts.put,
                on_speech=self._queue_whisper_speech,
                prompt_hint=self._whisper_prompt(),
            )
            self.whisper.start()

    def _whisper_prompt(self) -> str:
        """Spelling hint for Whisper: my name, roll number and the subject, in the mixed
        Urdu/English style the teacher uses. This makes '24K3074' and technical terms far more reliable."""
        student = self.student or {}
        bits = [str(student.get("roll_no", "")).replace("-", ""), str(student.get("name", ""))]
        bits += [str(n) for n in (student.get("urdu_names") or [])[:2]]
        bits = [b.strip() for b in bits if b and b.strip()]
        subject = str((self.cls or {}).get("subject", "")).strip()
        hint = ", ".join(dict.fromkeys(bits))
        if subject:
            hint += f", {subject}"
        hint += ". آپ مجھے بتائیں۔"
        return hint[:400]

    def _queue_whisper_speech(self, text, source):
        self._whisper_speech.put((text, source))

    def _record_whisper_transcripts(self):
        while True:
            try:
                text = self._whisper_texts.get_nowait()
            except queue.Empty:
                break
            if self.recorder is not None:
                self.recorder.add_audio_transcript(text)
        while True:
            try:
                text, source = self._whisper_speech.get_nowait()
            except queue.Empty:
                break
            if source == "microphone":
                self._handle_microphone_transcript(text)
            else:                       # the teacher's audio: listen for my name / roll number
                for sentence in _sentences(text):
                    self._process_sentence(sentence)

    def _handle_microphone_transcript(self, text):
        """The microphone also hears the speakers/room, so it gets the SAME rule as captions:
        answer only when my full name or roll number is called — never just because a question
        was heard."""
        for sentence in _sentences(" ".join(str(text or "").split())):
            self._process_sentence(sentence)

    def _me_called(self, text) -> bool:
        check = getattr(self.detector, "is_addressed", None)
        if callable(check):
            return bool(check(text))
        return bool(self.detector.is_name_mentioned(text) or self.detector.is_roll_mentioned(text))

    def _log_class_question(self, question, to_me=False, answer="", answered_by=""):
        recorder = getattr(self, "recorder", None)
        if recorder is not None and hasattr(recorder, "add_question"):
            try:
                recorder.add_question(question, to_me=to_me, answer=answer, answered_by=answered_by)
            except Exception as e:
                logger.debug(f"[Meet] Could not remember class question: {e!r}")

    async def _auto_sign_in(self):
        account  = self.config.get("google_account", {})
        email    = account.get("email", "")
        password = account.get("password", "")

        if not email or not password or password == "YOUR_PASSWORD_HERE":
            logger.error("[Meet] No credentials in config.")
            raise RuntimeError("Google credentials not configured")

        logger.info(f"[Meet] Auto signing in as: {email}")
        try:
            email_input = self.page.locator('input[type="email"]').first
            await email_input.wait_for(state="visible", timeout=10000)
            await email_input.fill(email)
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(2)

            pass_input = self.page.locator('input[type="password"]').first
            await pass_input.wait_for(state="visible", timeout=10000)
            await pass_input.fill(password)
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(3)

            if "accounts.google.com" in self.page.url:
                logger.warning("[Meet] 2FA required — waiting 2 minutes...")
                for _ in range(24):
                    await asyncio.sleep(5)
                    if "accounts.google.com" not in self.page.url:
                        break

            logger.info("[Meet] Sign-in complete.")
        except Exception as e:
            logger.error(f"[Meet] Auto sign-in failed: {e}")
            raise RuntimeError(f"Auto sign-in failed: {e}")

    async def _mute_mic(self, force=False):
        try:
            selectors = [
                'button[aria-label^="Microphone:"]',
                'div[aria-label^="Turn off microphone"]',
                '[aria-label="Turn off microphone"]'
            ]
            for sel in selectors:
                btn = self.page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    await asyncio.sleep(0.2)
                    logger.info("[Meet] Mic turned OFF.")
                    return
            if force:
                await self.page.keyboard.press("Control+D")
                logger.info("[Meet] Mic toggled via shortcut.")
        except Exception as e:
            logger.warning(f"[Meet] Mic mute failed: {e}")

    async def _mute_cam(self, force=False):
        try:
            selectors = [
                'button[aria-label^="Camera:"]',
                'div[aria-label^="Turn off camera"]',
                '[aria-label="Turn off camera"]'
            ]
            for sel in selectors:
                btn = self.page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    await asyncio.sleep(0.2)
                    logger.info("[Meet] Camera turned OFF.")
                    return
            if force:
                await self.page.keyboard.press("Control+E")
                logger.info("[Meet] Camera toggled via shortcut.")
        except Exception as e:
            logger.warning(f"[Meet] Camera off failed: {e}")

    async def _click_join(self):
        selectors = [
            'button:has-text("Join now")',
            'button:has-text("Ask to join")',
            'button:has-text("Join")',
        ]
        max_wait_mins = 30
        attempts = max_wait_mins * 6

        for attempt in range(attempts):
            for sel in selectors:
                try:
                    btn = self.page.locator(sel).first
                    if await btn.count() > 0:
                        await self._mute_mic(force=True)
                        await self._mute_cam(force=True)
                        await btn.click()
                        logger.info(f"[Meet] Clicked: {sel}")
                        await self.page.keyboard.press("Control+D")
                        await self.page.keyboard.press("Control+E")
                        try:
                            await self.page.wait_for_selector(
                                '[aria-label="Turn off microphone"]', timeout=5000
                            )
                            await self._mute_mic(force=True)
                        except Exception:
                            pass
                        try:
                            await self.page.wait_for_selector(
                                '[aria-label="Turn off camera"]', timeout=5000
                            )
                            await self._mute_cam(force=True)
                        except Exception:
                            pass
                        return
                except Exception:
                    pass

            if attempt % 12 == 0 and attempt > 0:
                waited = attempt // 6
                logger.info(f"[Meet] Waiting for meeting to start... ({waited}/{max_wait_mins} min)")

            await asyncio.sleep(10)

        raise RuntimeError(f"Join button not found after {max_wait_mins} minutes")

    async def _open_chat(self):
        if self._chat_opened:
            return
        try:
            btn = self.page.locator('[aria-label="Chat with everyone"]').first
            if await btn.count() > 0:
                await btn.click()
                await asyncio.sleep(1)
                self._chat_opened = True
                logger.info("[Meet] Chat opened.")
        except Exception as e:
            logger.warning(f"[Meet] _open_chat: {e}")

    async def _enable_captions(self):
        await asyncio.sleep(2)
        try:
            btn = self.page.locator('[aria-label="Turn on captions"]').first
            if await btn.count() > 0:
                await btn.click()
                await asyncio.sleep(2)
                logger.info("[Meet] Captions enabled.")
            else:
                logger.warning("[Meet] Captions button not found.")
                return
        except Exception as e:
            logger.warning(f"[Meet] Captions enable failed: {e}")
            return

        lang_key = (self.cls.get("captions") or self.features.get("caption_language") or "urdu").lower()
        if lang_key == "keep":
            logger.info("[Meet] Caption language: keeping Meet's own setting.")
            return
        lang_names = {
            "urdu": ["Urdu (Pakistan)"],
            "english": ["English (United States)", "English (India)", "English (United Kingdom)", "English"],
        }.get(lang_key, ["Urdu (Pakistan)"])

        try:
            settings_btn = self.page.locator('[aria-label="Open caption settings"]').first
            if await settings_btn.count() > 0:
                await settings_btn.evaluate("el => el.click()")
                await asyncio.sleep(1.5)
                logger.info("[Meet] Caption settings opened.")
            else:
                logger.warning("[Meet] Caption settings button not found.")
                return
        except Exception as e:
            logger.warning(f"[Meet] Caption settings failed: {e}")
            return

        try:
            result = await self.page.evaluate("""() => {
                const tabs = document.querySelectorAll('[jsname="z4Tpl"]');
                for (const tab of tabs) {
                    if ((tab.getAttribute('aria-label') || '').toLowerCase().includes('caption')) {
                        tab.click();
                        return 'clicked: ' + tab.getAttribute('aria-label');
                    }
                }
                return 'not found';
            }""")
            logger.info(f"[Meet] Captions tab: {result}")
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[Meet] Captions tab JS failed: {e}")

        try:
            result = await self.page.evaluate("""(names) => {
                const items = document.querySelectorAll('li, [role="option"]');
                for (const name of names) {
                    const byAria = document.querySelector('[aria-label^="' + name + '"]');
                    if (byAria) { byAria.click(); return 'clicked via aria: ' + name; }
                    for (const item of items) {
                        if (item.innerText && item.innerText.includes(name)) {
                            item.click();
                            return 'clicked via text: ' + item.innerText.slice(0, 30);
                        }
                    }
                }
                return 'not found';
            }""", lang_names)
            logger.info(f"[Meet] Caption language ({lang_key}): {result}")
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"[Meet] Caption language click failed: {e}")

        try:
            result = await self.page.evaluate("""() => {
                const selectors = [
                    '[aria-label="Close dialog"]',
                    '[aria-label="Close"]',
                    '[jsname="VdSJob"]',
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn) { btn.click(); return 'closed via: ' + sel; }
                }
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.innerText.includes('close') || btn.innerText.includes('Close')) {
                        btn.click();
                        return 'closed via text';
                    }
                }
                return 'not found';
            }""")
            logger.info(f"[Meet] Settings close: {result}")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"[Meet] Settings close JS failed: {e}")
            try:
                await self.page.keyboard.press("Escape")
                logger.info("[Meet] Settings closed via Escape.")
            except Exception:
                pass

    async def _read_chat(self) -> List[str]:
        """Other people's chat messages (never my own / the bot's own replies)."""
        msgs = []
        try:
            for sel in ['[jsname="xySENc"]', '.GDhqjd']:
                items = self.page.locator(sel)
                count = await items.count()
                if count > 0:
                    for i in range(count):
                        try:
                            t = await items.nth(i).inner_text()
                            msgs.extend(_parse_chat_messages(t))
                        except Exception:
                            pass
                    break
        except Exception:
            pass
        sent = self._sent_chat_norms
        return [m for m in msgs if " ".join(m.split()) not in sent]

    async def _chat_input_visible(self) -> bool:
        try:
            return await self.page.locator('[aria-label="Send a message"]').first.is_visible()
        except Exception:
            return False

    async def _ensure_chat_visible(self) -> bool:
        """The chat panel gets replaced by other side panels (e.g. caption settings).
        If the message box isn't visible, click the chat toggle until it is."""
        for _ in range(3):
            if await self._chat_input_visible():
                return True
            for sel in ('[aria-label="Chat with everyone"]', 'button[aria-label*="chat" i]'):
                try:
                    btn = self.page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.evaluate("el => el.click()")   # JS click: ignores overlays
                        await asyncio.sleep(1.2)
                        break
                except Exception:
                    continue
            else:
                await asyncio.sleep(1)
        self._chat_opened = await self._chat_input_visible()
        return self._chat_opened

    async def send_chat(self, message: str) -> bool:
        """Type + send a chat message quickly. Returns True if it was sent."""
        for attempt in (1, 2):
            try:
                if not await self._ensure_chat_visible():
                    logger.warning(f"[Meet] Chat box not visible (attempt {attempt})")
                    continue
                inp = self.page.locator('[aria-label="Send a message"]').first
                await inp.click(timeout=5000)
                await self.page.keyboard.press("Control+a")
                if attempt == 1 and len(message) > 12:
                    # Type two real keystrokes (so Meet wakes the Send button), paste the rest at once.
                    await self.page.keyboard.type(message[:2], delay=20)
                    await self.page.keyboard.insert_text(message[2:])
                    try:
                        typed = await inp.input_value(timeout=1500)
                    except Exception:
                        typed = message
                    if len(typed.strip()) < len(message) * 0.9:     # box did not take it: type slowly
                        await self.page.keyboard.press("Control+a")
                        await self.page.keyboard.type(message, delay=8)
                else:
                    await self.page.keyboard.type(message, delay=8 if len(message) > 40 else 30)
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(0.3)
                self._sent_chat_norms.add(" ".join(message.lower().split()))
                logger.info(f"[Meet] Sent: '{message}'")
                subj = "".join(c if c.isalnum() else "_" for c in self.cls.get("subject", "class"))
                # The screenshot is only a log: take it in the background so the reply is not delayed.
                asyncio.create_task(self._background_screenshot(f"screenshots/{subj}_{_time.strftime('%H%M%S')}_sent.png"))
                return True
            except Exception as e:
                logger.error(f"[Meet] send_chat error (attempt {attempt}): {str(e)[:200]}")
                self._chat_opened = False
        return False

    async def _background_screenshot(self, path):
        try:
            await self.screenshot(path)
        except Exception as e:
            logger.debug(f"[Meet] screenshot skipped: {e}")

    async def _read_captions(self) -> str:
        return " ".join(f"{speaker} {text}".strip()
                        for speaker, text in await self._read_caption_blocks())

    async def _read_caption_blocks(self):
        """Read visible Meet captions using the primary selector and known fallbacks."""
        selectors = list(dict.fromkeys(
            [MEET["caption_container"], *MEET["caption_fallbacks"]]
        ))
        try:
            raw = await self.page.evaluate("""(selectors) => {
                const isUi = text =>
                    /no chat messages yet|format_size|open caption settings|font size|font colour|returning to home screen|\\b\\d+\\s+seconds?\\s+left\\b|\\blanguage\\s*:\\s*english\\b/i.test(text);
                for (const selector of selectors) {
                    for (const container of document.querySelectorAll(selector)) {
                        const children = [...container.children]
                            .filter(child => (child.innerText || '').trim());
                        const lines = (children.length ? children : [container])
                            .map(child => child.innerText.trim())
                            .filter(text => text && !isUi(text));
                        if (lines.length) return lines;
                    }
                }
                return [];
            }""", selectors)
        except Exception:
            return []
        return _parse_caption_blocks(raw)

    async def _send_present(self, tg, cls, state, how: str) -> bool:
        """Send "Present Sir". Marks attendance ONLY if it was really sent; otherwise
        keeps retrying and alerts you so you can type it yourself."""
        self._present_tries += 1
        self._last_present_try = _time.time()
        ok = await self.send_chat("Present Sir")
        if ok:
            self._last_present_sent = _time.time()
            state.mark_attendance()
            self._pending_present = False
            tg.attendance_marked(cls, how)
            return True
        self._pending_present = True
        subj = cls.get("subject", "class")
        if self._present_tries == 1:
            self.alert.failure(subj, "Present was detected but could NOT be sent to chat. "
                                     "Retrying — if this persists, type it in the meeting yourself!")
        elif self._present_tries >= 5:
            self._pending_present = False
            self.alert.failure(subj, "Gave up sending Present after 5 tries — please type it in chat NOW.")
        return False

    async def _handle_present_request(self, tg, cls, state):
        """Act on a "Present Sir" request raised while listening (captions, microphone or meeting audio)."""
        request = self._present_request
        if not request or _time.time() < request["at"] + request["delay"]:
            return
        self._present_request = None
        if not state.get("attendance_marked"):
            logger.info(f"[Meet] {request['how']} — sending Present Sir")
            await self._send_present(tg, cls, state, request["how"])
        else:
            logger.info("[Meet] Attendance already marked - not answering the roll call again.")

    async def check_and_respond(self, tg, cls, state):
        already_sent = state.get("attendance_marked")
        self._attendance_marked = bool(already_sent)

        # A detected "Present" that failed to send → retry every 10s (max 5 tries)
        if self._pending_present and not already_sent and _time.time() - self._last_present_try >= 10:
            logger.info(f"[Meet] Retrying Present (try {self._present_tries + 1}/5)")
            await self._send_present(tg, cls, state, "Retry")
            already_sent = state.get("attendance_marked")

        # Read captions once so attendance detection and notes use the same text.
        blocks = await self._read_caption_blocks()
        cap = " ".join(f"{speaker} {text}".strip() for speaker, text in blocks)
        if not self._caption_check_started:
            self._caption_check_started = _time.time()
        if cap:
            if not self._caption_seen:
                logger.info("[Meet] Live captions detected; recording transcript.")
                self._caption_seen = True
            self.detector.add_caption(cap)
            if not self.captions or self.captions[-1] != cap:
                self.captions.append(cap)
                logger.info(f"[Meet] Caption: '{cap}'")
                state.update("last_caption", cap[-240:])
        elif (not self._caption_seen and not self._caption_warning_logged
              and _time.time() - self._caption_check_started >= 30):
            logger.warning(
                "[Meet] No live captions detected yet. Check that Meet captions are on, "
                "the caption language matches the speaker, and any YouTube tab audio is shared."
            )
            self._caption_warning_logged = True

        # Lecture notes + "you were called" alert
        if self.recorder is not None:
            touched = self.recorder.feed(blocks)
            self._record_whisper_transcripts()
            if self.features.get("called_alert", True):
                for seg in touched:
                    if not seg.alerted and self.alert.check(cls.get("subject", ""), seg.speaker, seg.text, tg, cls):
                        seg.alerted = True

        # Slide capture (throttled internally)
        if self.slides is not None:
            try:
                if await self.slides.tick(self.page):
                    state.update("slide_count", self.slides.count)
            except Exception as e:
                logger.debug(f"[Meet] slide tick error: {e}")

        # Read chat
        chat = await self._read_chat()
        if chat:
            signature = (len(chat), chat[-1])
            if signature != self._last_chat_log:      # log only when a new message arrives
                self._last_chat_log = signature
                logger.info(f"[Meet] Chat({len(chat)}): {str(chat[-1])[:120]}")
            self._check_for_addressed_chat_questions(chat)

        # Caption-based detection — pass raw caption directly (not joined deque)
        latest = cap if cap else (self.captions[-1] if self.captions else "")
        if not already_sent:
            result = self.detector.analyze(latest)
            if result == "mark_present":
                logger.info("[Meet] Attendance keyword or roll number — sending Present Sir")
                await self._send_present(tg, cls, state, "Roll call")
                # Do NOT reset detector — _present_sent stays True to block future sends
        else:
            self.detector.analyze(latest)
        self._check_for_addressed_question(blocks)
        await self._handle_present_request(tg, cls, state)

    def _check_for_addressed_question(self, blocks):
        now = _time.time()
        recall = getattr(self, "_recall", None)
        if recall and now - recall[0] >= 4:              # my name was called, no new question came
            self._recall = None
            self._queue_live_answer(recall[1])
        if now - self._pending_live_question_at > 90:
            self._pending_live_question = ""
        if now - self._pending_name_at > 45:
            self._pending_name_at = 0.0

        for index, (speaker, text) in enumerate(blocks):
            key = speaker or f"unknown-{index}"
            previous = self._question_caption_texts.get(key, "")
            if text.startswith(previous):
                delta = text[len(previous):]
            elif previous.startswith(text):
                delta = ""
            else:
                delta = text
            self._question_caption_texts[key] = text
            if not delta.strip():
                continue

            for sentence in _sentences(text)[-2:]:
                self._process_sentence(sentence)

    def _process_sentence(self, sentence):
        """Answer ONLY when I am called by full name / roll number.

        Every question heard in class is remembered for the notes, but a question put to
        another student is never answered.
        """
        now = _time.time()
        memory = self.__dict__.setdefault("_question_memory", [])
        memory[:] = [(t, q) for t, q in memory if now - t < 240][-8:]
        sentence = " ".join(str(sentence or "").split())
        if not sentence:
            return
        addressed = self._me_called(sentence)
        folded = _norm(sentence)
        has_wh = bool(_WH_WORD.search(folded))
        prompt_like = bool(_ANSWER_PROMPT.search(folded) or _CALL_ON.search(folded))
        real_question = (bool(_QUESTION_CUE.search(folded)) and (has_wh or len(sentence.split()) >= 5)
                         and (has_wh or not prompt_like))
        recent = self.__dict__.setdefault("_recent_sentences", deque(maxlen=6))
        if sentence not in recent:
            recent.append(sentence)
        if real_question and all(q != sentence for _, q in memory):
            memory.append((now, sentence))
            self._log_class_question(sentence)           # remembered for the notes only
        in_window = bool(self._pending_name_at and now - self._pending_name_at <= 20)
        # After I was asked something the teacher often fires follow-ups without repeating my
        # name; keep answering for a while, until another student is called.
        in_followup = now < getattr(self, "_followup_until", 0.0)
        if in_followup and not addressed and MeetHandler._calls_someone_else(self, sentence):
            self._followup_until = 0.0
            self._pending_name_at = 0.0
            in_window = in_followup = False
            self._recall = None
            logger.info("[Meet] Teacher moved on to another student; follow-up answering paused.")
        MeetHandler._attendance_from_speech(self, sentence, addressed,
                                            real_question or (prompt_like and MeetHandler._self_contained(self, folded)), now)
        handled = False
        if addressed:
            self._pending_name_at = now
            if real_question:
                question = sentence
            elif prompt_like and MeetHandler._self_contained(self, folded):   # "24K3074, tell me X and Y"
                question = sentence
            elif memory and MeetHandler._can_recall(self, memory[-1], now) and (
                    prompt_like or not MeetHandler._self_contained(self, folded)):
                # "Saad Naeem, you answer" / just "Saad Naeem?" -> the teacher means the question that
                # was asked a moment ago (e.g. to a student who stayed silent), without repeating it.
                question = memory[-1][1]
                if not prompt_like:                      # bare call: wait a beat for a NEW question
                    self._recall = (now, question)
                    question = ""
                    handled = True
            else:
                question = ""                            # roll call / name mention / unclear
            if question:
                self._queue_live_answer(question)
                handled = True
        elif real_question and (in_window or in_followup):
            self._pending_name_at = 0.0                  # question right after my name / follow-up
            self._recall = None                          # a fresh question beats the remembered one
            self._queue_live_answer(sentence)
            handled = True
        if not handled and (addressed or in_window or in_followup):
            # The word lists did not recognise a question (Urdu captions often have no "؟" and
            # use many phrasings), so let the AI decide - works for Urdu, English or a mix.
            ai_check = getattr(self, "_ai_check_question", None)
            if callable(ai_check):
                ai_check(sentence, addressed)

    def _can_recall(self, item, now) -> bool:
        """May I answer this remembered question now? Recent, not answered yet, and not in the
        middle of an unmarked roll call."""
        when, question = item
        if now - when > 120 or self._is_recent_duplicate(question, now):
            return False
        in_mode = now < getattr(self, "_attendance_mode_until", 0.0)
        return bool(getattr(self, "_attendance_marked", False) or not in_mode)

    def _calls_someone_else(self, sentence) -> bool:
        sentence = " ".join(str(sentence or "").split())
        if self._me_called(sentence):
            return False
        if _ANY_ROLL.search(sentence):
            return True
        match = _VOCATIVE.match(sentence)
        if match:
            return match.group(1).lower() not in _NOT_A_NAME
        tail = _TRAILING_NAME.search(sentence)
        return bool(tail and tail.group(1).lower() not in _NOT_A_NAME)

    def _attendance_from_speech(self, sentence, addressed, question_like, now):
        """Attendance heard in ANY language/source:
          * the teacher says "attendance" / "roll call" / "حاضری" / "अटेंडेंस"  -> Present Sir;
          * my name or roll number is called during attendance (or on its own before attendance was
            marked, and not as part of a question)                                -> Present Sir."""
        detector = getattr(self, "detector", None)
        keyword = bool(getattr(detector, "is_attendance_keyword", lambda _t: False)(sentence))
        marked = bool(getattr(self, "_attendance_marked", False))
        in_mode = now < getattr(self, "_attendance_mode_until", 0.0)
        if keyword:
            self._attendance_mode_until = now + 15 * 60
            if not marked or addressed:
                self._present_request = {"how": "Attendance keyword", "at": now, "delay": 0.0, "explicit": addressed}
        elif addressed and not question_like:
            if in_mode:
                self._present_request = {"how": "Called during attendance", "at": now, "delay": 0.0, "explicit": True}
            elif not marked:
                # A bare call ("24K3074") may be the start of a question: give it a moment first.
                self._present_request = {"how": "Roll call", "at": now, "delay": 4.0, "explicit": True}

    def _self_contained(self, folded) -> bool:
        """True when the sentence itself says WHAT to answer ('tell me the difference between P and
        NP') rather than just calling on me ('Saad Naeem, you answer')."""
        student = getattr(getattr(self, "detector", None), "student", None) or {}
        names = {w for n in [student.get("name", ""), *student.get("urdu_names", [])]
                 for w in _tokens(_norm(n))}
        words = [w for w in _tokens(folded)
                 if w not in _FILLER and w not in names and not any(c.isdigit() for c in w)
                 and not _ANSWER_PROMPT.fullmatch(w) and not _CALL_ON.fullmatch(w)]
        return len(words) >= 3

    def _ai_check_question(self, sentence, addressed):
        if not self._answers_enabled():
            return
        if len(sentence.split()) < (4 if addressed else 3):   # bare name / filler: wait for more
            return
        if not ai_notes.api_key(self.config):
            return
        now = _time.time()
        if now - self._ai_window_start > 30:
            self._ai_window_start, self._ai_calls = now, 0
        if self._ai_calls >= 3:
            return
        for task in (self._ai_check_task, self._question_answer_task):
            if task and not task.done():
                return
        lines = list(self._recent_sentences)[-3:]
        key = " ".join(lines)
        if key in self._ai_checked:
            return
        try:
            task = asyncio.create_task(self._ai_extract_question(lines))
        except RuntimeError:                              # no running event loop
            return
        if len(self._ai_checked) > 200:
            self._ai_checked.clear()
        self._ai_checked.add(key)
        self._ai_calls += 1
        self._ai_check_task = task

    async def _ai_extract_question(self, lines):
        try:
            question = await asyncio.to_thread(
                ai_notes.extract_addressed_question, self.config, lines,
                str(self.student.get("name", "")),
            )
        except Exception as e:
            logger.error(f"[Meet] AI question check failed: {e}")
            return
        if question:
            logger.info(f"[Meet] AI recognised a question addressed to me: {question}")
            self._queue_live_answer(question)

    def _check_for_addressed_chat_questions(self, messages):
        for message in messages:
            normalized = " ".join(str(message or "").casefold().split())
            if not normalized or normalized in self._seen_chat_message_set:
                continue
            self._remember_chat_message(normalized)
            if normalized in self._sent_chat_norms:       # something I typed myself
                continue
            if self._me_called(normalized):
                folded = _norm(normalized)
                if _QUESTION_CUE.search(folded) or _ANSWER_PROMPT.search(folded):
                    self._queue_live_answer(message)

    def _remember_chat_message(self, message):
        normalized = " ".join(str(message or "").casefold().split())
        if not normalized or normalized in self._seen_chat_message_set:
            return
        self._seen_chat_message_set.add(normalized)

    def _topic_words(self, text) -> set:
        return {t for t in _tokens(_norm(text))
                if len(t) >= 2 and t not in _FILLER and not any(c.isdigit() for c in t)}

    def _is_recent_duplicate(self, question, now) -> bool:
        words = self._topic_words(question)
        if not words:
            return False
        for when, old in getattr(self, "_recent_answered", ()):
            if now - when <= 90 and old and len(words & old) / min(len(words), len(old)) >= 0.6:
                return True
        return False

    def _answers_enabled(self) -> bool:
        return bool((getattr(self, "features", None) or {}).get("answer_questions", True))

    def _queue_live_answer(self, question):
        if not self._answers_enabled():
            # Preference is OFF: stay silent, but still remember the question for the notes.
            if not getattr(self, "_answers_off_logged", False):
                logger.info("[Meet] 'Answer questions in chat' is OFF - not replying (questions are still noted).")
                self._answers_off_logged = True
            self._log_class_question(question, to_me=True)
            return
        now = _time.time()
        normalized = " ".join(re.sub(r"\W+", " ", question.casefold()).split())
        if not normalized or normalized == self._last_queued_question:
            return
        if self._question_answer_task and not self._question_answer_task.done():
            # a follow-up arrived while the previous answer is being written: answer it next
            deferred = self.__dict__.setdefault("_deferred_questions", [])
            if len(deferred) < 2 and all(normalized != d[0] for d in deferred):
                deferred.append((normalized, question))
                logger.info("[Meet] Follow-up question queued; answering it right after this one.")
            return
        # The teacher's voice reaches me through captions, the microphone AND the meeting audio,
        # each spelling it differently - so after one answer ignore repeats for a short while.
        if now < getattr(self, "_answer_block_until", 0.0):
            logger.debug("[Meet] Just answered a question; ignoring the repeat of it.")
            return
        if self._is_recent_duplicate(question, now):
            logger.debug("[Meet] Same question as one I already answered; skipping.")
            return
        self._last_queued_question = normalized
        request = getattr(self, "_present_request", None)
        if request and request.get("delay"):          # it was a question, not a roll call
            self._present_request = None
        self._answer_block_until = now + 8          # only to swallow the same sentence heard twice
        self._followup_until = now + 75             # keep listening for follow-ups
        self._recent_answered.append((now, self._topic_words(question)))
        self._log_class_question(question, to_me=True)
        self._pending_live_question = ""
        self._pending_live_question_at = 0.0
        self._pending_name_at = 0.0
        self._question_answer_task = asyncio.create_task(self._answer_live_question(question))

    def _pop_deferred(self):
        deferred = self.__dict__.get("_deferred_questions") or []
        if deferred:
            _, question = deferred.pop(0)
            self._answer_block_until = 0.0
            self._queue_live_answer(question)

    async def _answer_live_question(self, question):
        try:
            await self._answer_live_question_inner(question)
        finally:
            if self.__dict__.get("_deferred_questions"):
                try:
                    asyncio.get_running_loop().call_later(0.5, self._pop_deferred)
                except RuntimeError:
                    pass

    async def _answer_live_question_inner(self, question):
        if not ai_notes.api_key(self.config):
            if not self._missing_question_key_logged:
                logger.warning(
                    "[Meet] Cannot answer live questions without an AI provider key. "
                    "Add one in Dashboard → Settings → AI."
                )
                self._missing_question_key_logged = True
            return

        context = self.recorder._plain() if self.recorder is not None else ""
        if not context.strip():
            context = "\n".join(self.captions)
        context = context[-2500:]        # recent lecture only: a huge prompt makes the reply very slow
        try:
            answer = await asyncio.to_thread(
                ai_notes.answer_question, self.config, context, question, None, True
            )
            if not answer:
                logger.warning("[Meet] The AI provider could not answer the live question.")
                return
            if len(answer) > 1600:
                answer = answer[:1597].rsplit(" ", 1)[0] + "..."
            who = dict(getattr(ai_notes, "LAST_LIVE_REPLY", {}) or {})
            by = (f"{who.get('provider', '?').title()} ({who.get('model', '?')})"
                  if who.get("provider") else "unknown provider")
            if not await self.send_chat(answer):
                logger.error("[Meet] Could not send the live question answer to meeting chat.")
            else:
                logger.info(f"[Meet] Answer written by {by} in {who.get('seconds', 0):.1f}s")
                self._log_class_question(question, to_me=True, answer=answer,
                                         answered_by=who.get("provider", ""))
            self._answer_block_until = max(self._answer_block_until, _time.time() + 4)
        except Exception as e:
            logger.error(f"[Meet] Live question answering failed: {e}")

    def _name_in_captions(self) -> bool:
        text = " ".join(self.captions).lower()
        return any(n.lower() in text for n in self.student["urdu_names"])

    _END_PHRASES = (
        "the meeting has ended", "this meeting has ended", "meeting has ended",
        "host ended the meeting", "your host ended the meeting for everyone",
        "you've been removed from the meeting", "you were removed from the meeting",
        "you've left the meeting", "you left the meeting", "call ended",
        "returning to home screen", "ended the meeting for everyone",
        "return to home screen", "submit feedback", "how was the audio and video",
        "میٹنگ ختم ہو گئی",
    )
    # lobby / reconnect screens where the call controls are missing but the class is NOT over
    _WAITING = re.compile(
        r"asking to be let in|ask to join|someone will let you in|waiting for the host|"
        r"let you in soon|joining\.\.\.|reconnecting|trying to reconnect|you.re offline",
        re.IGNORECASE,
    )

    async def is_meeting_ended(self) -> bool:
        """True as soon as the class is over, whatever the scheduled duration is:
        the host ended it, the bot was removed, the call page closed, or the bot has been
        alone for `end_when_alone_secs` after the lecture had really started."""
        now = _time.time()
        if now - self._end_checked_at < 2:           # cheap: look at the page every 2 s
            return bool(self.end_reason)
        self._end_checked_at = now
        if self.end_reason:
            return True
        try:
            if self.page is None or self.page.is_closed():
                self.end_reason = "meeting page closed"
                return True
            info = await self.page.evaluate(
                """() => ({
                    inCall: !!document.querySelector('[aria-label="Leave call"]'),
                    text: (document.body ? document.body.innerText : '').toLowerCase().slice(0, 30000),
                    url: location.href,
                })"""
            )
        except Exception as e:
            logger.debug(f"[Meet] Could not check for meeting end screen: {e!r}")
            return False
        if not isinstance(info, dict):
            return False
        text, url, in_call = info.get("text", ""), info.get("url", ""), bool(info.get("inCall"))
        online = info.get("online", True) is not False
        if in_call:
            self._was_in_call = True

        ended = weak = False
        if not in_call and self._was_in_call and online:
            # call controls are gone: end screen text, or we were sent back out of the meeting
            on_end_screen = any(p in text for p in self._END_PHRASES)
            left_meeting = bool(self._meeting_code) and self._meeting_code not in url.lower()
            ended = on_end_screen or left_meeting
            # No end text recognised (Google changed the wording / language)? Controls missing
            # for several checks in a row on a non-lobby page still means the call is over.
            weak = not ended and not self._WAITING.search(text)
        self._end_hits = self._end_hits + 1 if ended else 0
        self._weak_hits = self._weak_hits + 1 if weak else 0
        if self._end_hits >= 2 or self._weak_hits >= 4:   # a flicker can't end the class
            self.end_reason = "host ended the meeting / bot left the call"
            logger.info(f"[Meet] End of class detected ({self.end_reason}).")
            return True

        # Everyone (teacher included) left and only the bot remains -> class is over.
        class_started = bool(self.recorder is not None and self.recorder.segments)
        alone = in_call and ("you're the only one here" in text or "you are the only one here" in text)
        if alone and class_started:
            self._alone_since = self._alone_since or now
            limit = float(self.settings.get("end_when_alone_secs", 120))
            if now - self._alone_since >= limit:
                self.end_reason = "everyone left the meeting"
                logger.info(f"[Meet] Bot has been alone for {int(limit)}s after class — ending.")
                return True
        else:
            self._alone_since = 0.0
        return False

    def stop_audio(self):
        """Stop local transcription and save whatever it already heard (called as class ends)."""
        if self.whisper is not None:
            try:
                self.whisper.stop()
            except Exception as e:
                logger.warning(f"[Meet] Could not stop local transcription cleanly: {e}")
            self.whisper = None
        try:
            self._record_whisper_transcripts()
        except Exception as e:
            logger.debug(f"[Meet] Could not save final audio transcripts: {e!r}")
        if self.recorder is not None:
            self.recorder.flush()

    async def screenshot(self, path: str):
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=path)
        except Exception:
            pass

    async def leave(self):
        self.stop_audio()
        try:
            btn = self.page.locator('[aria-label="Leave call"]').first
            if await btn.count() > 0:
                await btn.click()
                await asyncio.sleep(2)
        except Exception:
            pass
        finally:
            try:
                await self.context.close()
                await self.playwright.stop()
            except Exception:
                pass