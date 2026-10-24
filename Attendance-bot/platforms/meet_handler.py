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
from detection.burst_detector import BurstDetector
from detection.whisper_asr import WhisperRecognizer
from core import config_store
from utils.alerts import CalledAlert
from utils.slide_capture import SlideCapture
from utils.selectors import MEET

logger = setup_logger("MeetHandler")

_CAPTION_UI = re.compile(
    r"no chat messages yet|format_size|open caption settings|font size|font colour|"
    r"returning to home screen|\b\d+\s+seconds?\s+left\b|"
    r"\blanguage\s*:\s*english\b",
    re.IGNORECASE,
)


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
        self.burst       = BurstDetector()
        self.captions: deque = deque(maxlen=50)
        self._chat_opened = False
        self._low_count_since: float = 0.0  # grace period for low participant count
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
        if (self.recorder is not None and self.recorder.enabled
                and self.features.get("whisper_transcription", True)):
            self.whisper = WhisperRecognizer(on_transcript=self._whisper_texts.put)
            self.whisper.start()

    def _record_whisper_transcripts(self):
        if self.recorder is None:
            return
        while True:
            try:
                text = self._whisper_texts.get_nowait()
            except queue.Empty:
                break
            self.recorder.add_audio_transcript(text)

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
        msgs = []
        try:
            for sel in ['[jsname="xySENc"]', '.GDhqjd']:
                items = self.page.locator(sel)
                count = await items.count()
                if count > 0:
                    for i in range(count):
                        try:
                            t = await items.nth(i).inner_text()
                            if t.strip():
                                msgs.append(t.strip().lower())
                        except Exception:
                            pass
                    break
        except Exception:
            pass
        return msgs

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
        """Type + send a chat message. Returns True if it was sent."""
        for attempt in (1, 2):
            try:
                if not await self._ensure_chat_visible():
                    logger.warning(f"[Meet] Chat box not visible (attempt {attempt})")
                    continue
                inp = self.page.locator('[aria-label="Send a message"]').first
                await inp.click(timeout=5000)
                await asyncio.sleep(0.3)
                await self.page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await self.page.keyboard.type(message, delay=30)
                await asyncio.sleep(0.3)
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(0.8)
                logger.info(f"[Meet] Sent: '{message}'")
                subj = "".join(c if c.isalnum() else "_" for c in self.cls.get("subject", "class"))
                await self.screenshot(f"screenshots/{subj}_{_time.strftime('%H%M%S')}_sent.png")
                return True
            except Exception as e:
                logger.error(f"[Meet] send_chat error (attempt {attempt}): {str(e)[:200]}")
                self._chat_opened = False
        return False

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
        """Send "Present". Marks attendance ONLY if it was really sent; otherwise
        keeps retrying and alerts you so you can type it yourself."""
        self._present_tries += 1
        self._last_present_try = _time.time()
        ok = await self.send_chat("Present")
        if ok:
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

    async def check_and_respond(self, tg, cls, state):
        already_sent = state.get("attendance_marked")

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
            logger.info(f"[Meet] Chat({len(chat)}): {str(chat[-2:])[:120]}")

        # Burst detection
        count, burst = self.burst.check_with_count(chat)
        if count > 0:
            logger.info(f"[Meet] Burst count={count} triggered={burst} already_sent={already_sent}")

        if burst and not already_sent:
            logger.info("[Meet] BURST — sending Present")
            tg.burst_detected(cls, count)
            await self._send_present(tg, cls, state, "Burst")
            self.detector.reset()
            return

        # Caption-based detection — pass raw caption directly (not joined deque)
        latest = cap if cap else (self.captions[-1] if self.captions else "")
        if not already_sent:
            result = self.detector.analyze(latest)
            if result == "mark_present":
                logger.info("[Meet] Roll call — sending Present")
                await self._send_present(tg, cls, state, "Roll call")
                # Do NOT reset detector — _present_sent stays True to block future sends
            elif result == "question_asked":
                logger.info("[Meet] Question — sending Mic kharab hai")
                await self.send_chat("Mic kharab hai")
        else:
            if burst:
                logger.info("[Meet] Burst detected but Present already sent — ignoring")
            self.detector.analyze(latest)

    def _name_in_captions(self) -> bool:
        text = " ".join(self.captions).lower()
        return any(n.lower() in text for n in self.student["urdu_names"])

    async def is_meeting_ended(self) -> bool:
        """
        Returns True when meeting is fully ended for everyone.
        Also returns True if participant count < 5 for 2 consecutive minutes.
        """
        try:
            # End screen detection
            phrases = [
                "The meeting has ended",
                "meeting has ended",
                "میٹنگ ختم ہو گئی",
                "Host ended the meeting",
                "Your host ended the meeting for everyone",
            ]
            for phrase in phrases:
                if await self.page.locator(f':has-text("{phrase}")').count() > 0:
                    logger.info("[Meet] End screen detected.")
                    return True

            # Participant count via JavaScript (most reliable)
            count = await self._get_participant_count()
            if count > 0:
                logger.info(f"[Meet] Participant count: {count}")
                min_p = config_store.min_participants(self.config)
                if count < min_p:
                    if self._low_count_since == 0.0:
                        self._low_count_since = _time.time()
                        logger.info(f"[Meet] Count={count} < {min_p} — 2min grace started")
                    elif _time.time() - self._low_count_since >= 120:
                        logger.info(f"[Meet] Count < {min_p} for 2min — leaving.")
                        return True
                else:
                    if self._low_count_since > 0.0:
                        logger.info(f"[Meet] Count back to {count} — grace reset")
                    self._low_count_since = 0.0

        except Exception:
            pass
        return False

    async def _get_participant_count(self) -> int:
        """Get participant count via JavaScript — most reliable method."""
        try:
            count = await self.page.evaluate("""() => {
                // Method 1: people button aria-label e.g. "People (25)"
                const btns = document.querySelectorAll('button, [role="button"]');
                for (const btn of btns) {
                    const aria = btn.getAttribute('aria-label') || '';
                    const match = aria.match(/\((\d+)\)/);
                    if (match && (aria.toLowerCase().includes('people') ||
                                  aria.toLowerCase().includes('participant'))) {
                        return parseInt(match[1]);
                    }
                }
                // Method 2: count video tiles (each participant has one)
                const tiles = document.querySelectorAll('[jsname="kAPMuc"]');
                if (tiles.length > 0) return tiles.length;

                // Method 3: participant list items
                const items = document.querySelectorAll('[data-participant-id]');
                if (items.length > 0) return items.length;

                return 0;
            }""")
            return count or 0
        except Exception:
            pass
        return 0

    async def screenshot(self, path: str):
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=path)
        except Exception:
            pass

    async def leave(self):
        if self.whisper is not None:
            self.whisper.stop()
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