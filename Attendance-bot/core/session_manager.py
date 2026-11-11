"""
Session Manager — orchestrates joining, monitoring, and leaving.

Timing rules (all relative to scheduled class time in JSON):
1. Join 2 min after scheduled start
2. Keep trying to join for up to 20 min from scheduled start
3. Leave at: scheduled_end + 5 min, OR as soon as the class really ends (host ends the
   meeting / everyone leaves) — the notes are generated right away in both cases
4. Rejoin if host ends early, until class_end + 5 min
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from core.logger import setup_logger
from platforms.meet_handler import MeetHandler
from platforms.zoom_handler import ZoomHandler
from utils.state_store import StateStore
from utils.attendance_logger import AttendanceLogger
from utils.telegram_notifier import TelegramNotifier
from utils.notes_recorder import NotesRecorder

logger = setup_logger("SessionManager")
PKT = ZoneInfo("Asia/Karachi")


class SessionManager:
    _live_sessions = 0          # classes currently being attended (shared by all sessions)
    _notes_tasks: set = set()   # notes still being written in the background

    @classmethod
    async def wait_all_notes(cls, timeout: float = 1200):
        """Wait for notes of every finished class (used on shutdown / test mode)."""
        pending = [t for t in cls._notes_tasks if not t.done()]
        if pending:
            logger.info(f"Waiting for {len(pending)} notes job(s) to finish...")
            await asyncio.wait(pending, timeout=timeout)

    def __init__(self, config: Dict):
        self.config      = config
        self.settings    = config["global_settings"]
        self.student     = config["student"]
        self.state       = StateStore()
        self.att_logger  = AttendanceLogger()
        self.tg          = TelegramNotifier(config)
        self.current_handler = None
        self.current_recorder = None
        self._notes_task = None

    async def finalize_notes(self):
        """Finish the active session's notes once, even if shutdown also triggers cleanup."""
        if self.current_recorder is None:
            self.state.set_idle()
            return
        task = self.start_notes_finalization()
        await asyncio.shield(task)

    def start_notes_finalization(self):
        """Start finalizing immediately after leaving, without blocking status updates."""
        if self.current_recorder is None:
            self.state.set_idle()
            return None
        if not self.current_recorder.enabled:
            self.state.set_idle()
            return None
        if self._notes_task is None:
            if SessionManager._live_sessions <= 1:      # don't hide a class that is running
                self.state.set_status("generating_notes")
            self._notes_task = asyncio.create_task(self._finalize_notes(self.current_recorder))
            SessionManager._notes_tasks.add(self._notes_task)
            self._notes_task.add_done_callback(SessionManager._notes_tasks.discard)
        return self._notes_task

    async def _finalize_notes(self, recorder):
        try:
            try:
                done = await asyncio.wait_for(recorder.finalize(), timeout=1200)
            except asyncio.TimeoutError:
                raise
            except Exception as first:        # one automatic retry (network blips, API hiccups)
                logger.warning(f"[{recorder.subject}] Notes failed ({first}); retrying in 30 s.")
                await asyncio.sleep(30)
                done = await asyncio.wait_for(recorder.finalize(), timeout=1200)
            if done:
                self.state.update("last_notes", str(done))
                tg = getattr(self, "tg", None)
                if tg is not None:
                    tg.notes_ready(recorder.cls, str(done))
        except Exception as e:
            logger.error(f"[{recorder.subject}] Could not finish notes: {e}")
        finally:
            if SessionManager._live_sessions == 0:      # a newer class may already be running
                self.state.set_idle()

    async def attend(self, cls: Dict, is_last: bool = True):
        SessionManager._live_sessions += 1
        try:
            await self._attend(cls, is_last)
        finally:
            SessionManager._live_sessions = max(0, SessionManager._live_sessions - 1)

    async def _attend(self, cls: Dict, is_last: bool = True):
        platform = cls["platform"]
        subject  = cls["subject"]

        # Skip if no link
        link = cls.get("link", "").strip()
        if not link:
            logger.warning(f"[{subject}] No link — skipping.")
            return

        self.state = StateStore()
        self.state.set_current_class(cls)

        # All times relative to scheduled start in JSON
        scheduled_start = self._scheduled_start(cls)
        hard_end        = scheduled_start + timedelta(
            minutes=cls["duration"] + 5  # scheduled_end + 5 min
        )

        logger.info(
            f"[{subject}] Session | "
            f"scheduled={scheduled_start.strftime('%H:%M')} "
            f"hard_end={hard_end.strftime('%H:%M')}"
        )

        handler = self._get_handler(platform, cls)
        self.current_handler = handler

        # Lecture notes + slides (Meet only — Zoom has no captions to read)
        recorder = NotesRecorder(cls, self.config) if platform == "meet" else None
        self.current_recorder = recorder
        if recorder is not None and hasattr(handler, "attach_recorder"):
            handler.attach_recorder(recorder)
            self.state.update("notes_dir", str(recorder.dir) if recorder.enabled else "")
        session_start = time.time()
        joined = False

        # ── Join phase ──────────────────────────────────────
        # Try joining until 20 min after scheduled start
        join_deadline = scheduled_start + timedelta(minutes=20)
        attempt = 0
        while datetime.now(PKT) <= join_deadline:
            attempt += 1
            try:
                await handler.join()
                logger.info(f"[{subject}] Joined (attempt {attempt})")
                self.tg.joined(cls)
                joined = True
                break
            except RuntimeError as e:
                err = str(e)
                # Hard stop — no point retrying these
                if "No link" in err or "skipping" in err.lower():
                    logger.warning(f"[{subject}] {err} — skipping class.")
                    self.current_handler = None
                    self.state.set_idle()
                    if recorder is not None:
                        await self.finalize_notes()
                    return
                logger.warning(f"[{subject}] Join attempt {attempt} failed: {err}")
                remaining = (join_deadline - datetime.now(PKT)).total_seconds()
                if remaining > 0:
                    await asyncio.sleep(min(30, remaining))
            except Exception as e:
                logger.warning(f"[{subject}] Join attempt {attempt} failed: {e}")
                remaining = (join_deadline - datetime.now(PKT)).total_seconds()
                if remaining > 0:
                    await asyncio.sleep(min(30, remaining))

        if not joined:
            logger.error(f"[{subject}] Could not join within 20 min — skipping.")
            self.tg.error(cls, "Could not join within 20 min")
            self.att_logger.log_failure(cls, "Join timeout")
            self.current_handler = None
            self.state.set_idle()
            if recorder is not None:
                await self.finalize_notes()
            return

        self.state.mark_joined()

        # ── Monitor + Rejoin phase ──────────────────────────
        try:
            await self._monitor_with_rejoin(handler, cls, hard_end)
        except Exception as e:
            logger.exception(f"[{subject}] Session error: {e}")
            self.tg.error(cls, str(e))
        finally:
            duration_secs = int(time.time() - session_start)
            # Class is over (early or on time): freeze the recording and start the notes NOW,
            # in parallel with leaving the call, instead of waiting for the scheduled end.
            stop_audio = getattr(handler, "stop_audio", None)
            if callable(stop_audio):
                try:
                    await asyncio.to_thread(stop_audio)
                except Exception as e:
                    logger.warning(f"[{subject}] Could not stop audio capture cleanly: {e}")
            notes_task = self.start_notes_finalization()
            if notes_task is not None:
                now = datetime.now(PKT)
                early = int((hard_end - now).total_seconds() // 60) - 5
                why = getattr(handler, "end_reason", "") or "scheduled end time"
                logger.info(
                    f"[{subject}] Class over at {now:%H:%M} ({why}"
                    + (f", {early} min before schedule" if early > 0 else "")
                    + ") — generating notes now."
                )
                await asyncio.sleep(0)
            try:
                await handler.leave()
            except Exception as e:
                logger.error(f"[{subject}] Could not leave meeting cleanly: {e}")
            self.current_handler = None
            self.tg.left(cls, "host_ended" if getattr(handler, "end_reason", "") else "end_time")
            self.tg.class_summary(cls, self.state.get("attendance_marked"), duration_secs)
            self.att_logger.log_session(cls, marked=bool(self.state.get("attendance_marked")))
            # Notes keep generating in the background so the NEXT class (even 10 min later)
            # is joined on time; shutdown waits for them via wait_all_notes().
            logger.info(f"[{subject}] Session ended.")

    async def _monitor_with_rejoin(self, handler, cls: Dict, hard_end: datetime):
        """
        Leave ONLY when one of these conditions is met:
        1. scheduled_end + 5min reached (hard_end)
        2. Host ended the meeting for everyone
        A low participant count is not treated as a meeting end: teachers may stay
        alone while preparing the class, and participants can leave temporarily.
        """
        platform = cls["platform"]
        subject  = cls["subject"]

        logger.info(f"[{subject}] Monitoring until {hard_end.strftime('%H:%M')}")

        while True:
            now = datetime.now(PKT)

            # Case 1: Time up
            if now >= hard_end:
                logger.info(f"[{subject}] End time {hard_end.strftime('%H:%M')} reached — leaving.")
                break

            # Case 2 & 3: Meeting ended (host ended or count < 5 for 2min)
            if await handler.is_meeting_ended():
                logger.info(f"[{subject}] Meeting ended — leaving.")
                self.tg.class_ended_by_host(cls)
                break

            # Meet: run attendance detection
            if platform == "meet":
                await handler.check_and_respond(self.tg, cls, self.state)

            await asyncio.sleep(1)

    def _scheduled_start(self, cls: Dict) -> datetime:
        """Returns scheduled start as timezone-aware datetime (PKT)."""
        now = datetime.now(PKT)
        h, m = map(int, cls["time"].split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # If scheduled time already passed today, it's still today
        return start

    def _get_handler(self, platform: str, cls: Dict):
        if platform == "meet":
            return MeetHandler(cls, self.config)
        elif platform == "zoom":
            return ZoomHandler(cls, self.config)
        else:
            raise ValueError(f"Unknown platform: {platform}")

    def _get_next_class(self, cls: Dict) -> Optional[Dict]:
        today = cls["day"]
        h, m  = map(int, cls["time"].split(":"))
        this_end = h * 60 + m + cls.get("duration", 60)
        candidates = []
        for other in self.config["classes"]:
            if other["day"] != today:
                continue
            if other["subject"] == cls["subject"] and other["time"] == cls["time"]:
                continue
            oh, om = map(int, other["time"].split(":"))
            if oh * 60 + om >= this_end:
                candidates.append((oh * 60 + om, other))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]