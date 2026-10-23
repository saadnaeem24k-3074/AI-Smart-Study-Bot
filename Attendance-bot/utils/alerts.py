"""
"You were called" alerts.

Fires a loud local alert (beeps + always-on-top popup, Windows) when the
teacher/anyone says your name or roll number in the live captions, so you can
jump in if the bot can't answer for you. Also used when the bot FAILS to send
"Present", so you can type it yourself.
"""

import re
import sys
import threading
import time
from typing import Dict, Iterable, List, Optional

from core.logger import setup_logger
from detection.attendance_detector import NAME_EXACT, ROLL_PATTERNS
from utils.state_store import StateStore

logger = setup_logger("Alerts")

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


class NameMatcher:
    """Whole-word match of your name variants (so 'فساد' does NOT match 'ساد')."""

    def __init__(self, config: Dict):
        student = config.get("student", {})
        variants = list(NAME_EXACT) + list(student.get("urdu_names", []))
        if student.get("name"):
            variants.append(student["name"])
        seqs = set()
        for v in variants:
            t = tuple(_tokens(v))
            if t:
                seqs.add(t)
        self._seqs = sorted(seqs, key=len, reverse=True)

    def matches(self, text: str) -> bool:
        toks = _tokens(text)
        if any(p.search(text or "") for p in ROLL_PATTERNS):
            return True
        for seq in self._seqs:
            n = len(seq)
            for i in range(len(toks) - n + 1):
                if tuple(toks[i:i + n]) == seq:
                    return True
        return False


class CalledAlert:
    def __init__(self, config: Dict, cooldown: float = 45.0):
        self.matcher = NameMatcher(config)
        self.cooldown = cooldown
        self._last = 0.0
        self.state = StateStore()

    def check(self, subject: str, speaker: str, text: str, tg=None, cls: Optional[Dict] = None) -> bool:
        if not self.matcher.matches(text):
            return False
        now = time.time()
        if now - self._last < self.cooldown:
            return False
        self._last = now
        msg = f"{speaker or 'Someone'}: {text[-160:]}"
        logger.warning(f"[{subject}] YOU WERE CALLED → {msg}")
        self.state.add_alert("called", subject, msg)
        notify(f"{subject}: you were called!", msg)
        if tg is not None and cls is not None:
            try:
                tg.name_detected(cls, "you", msg)
            except Exception:
                pass
        return True

    def failure(self, subject: str, text: str):
        logger.error(f"[{subject}] {text}")
        self.state.add_alert("failure", subject, text)
        notify(f"{subject}: ACTION NEEDED", text)


def notify(title: str, text: str) -> None:
    """Beeps + topmost popup. No-op (log only) on non-Windows."""
    def _run():
        try:
            if sys.platform != "win32":
                return
            import ctypes
            import winsound
            for _ in range(3):
                winsound.Beep(1200, 220)
                time.sleep(0.08)
            MB_ICONWARNING, MB_TOPMOST, MB_SETFOREGROUND = 0x30, 0x40000, 0x10000
            ctypes.windll.user32.MessageBoxW(
                0, text, f"Attendance Bot — {title}",
                MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND,
            )
        except Exception as e:  # never let an alert crash the bot
            logger.debug(f"notify failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
