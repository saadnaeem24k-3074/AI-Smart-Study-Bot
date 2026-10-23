"""
Attendance Detector - Delta-based. Fully debugged.
"""

import re
import time
from typing import Literal
from core.logger import setup_logger

logger = setup_logger("AttendanceDetector")

ATTENDANCE_EXACT = [
    "اٹینڈنس", "ٹینڈنس", "اٹینڈینس",
    "اٹندڈن", "ٹندڈنس", "اٹندڈنس",
    "پریزنٹ", "پرزنٹ", "رول نمبر",
    "اٹینڈنس مارک", "اٹینڈنس مارک کروا لیں",
    "اٹینڈنس مارک کر رہا ہوں","انٹرنس","ہنڈرنس","اٹینڈنس مارک کر رہی ہوں",
    "attendance", "attendance mark",
    "attendance mark kar raha hun", "attendance mark kar rahi hun",
    "attendance lgwa lain", "attendance lagwa lain",
    "attendance call kar raha hun", "attendance call kar rahi hun",
]

NAME_EXACT = [
    # Full name (Urdu) + common speech-to-text variants
    "سعد نعیم", "ساد نعیم", "سات نعیم", "سعد نائم", "ساد نائم",
    "سعد نئیم", "ساد نئیم", "صعد نعیم", "سد نعیم", "سعت نعیم",
    "سعد نعیم", "سعد نیم", "ساد نیم",
    # First name only (Urdu)
    "سعد", "ساد", "سات", "صعد", "سد",
    # English
    "saad naeem", "saad naim", "saad nayeem", "sad naeem",
    "saad",
]

# Specific to roll 24K-3074 only
# Urdu STT renders: 24کے3074, 24کے 30 74, 24کے تھری زیرو سیون فور etc
ROLL_PATTERNS = [
    # English captions: "twenty four K three zero seven four"
    re.compile(r"(24|twenty[\s-]*four)\s*[kK]\s*-?\s*(three|3)\s*(zero|oh|0)\s*(seven|7)\s*(four|4)", re.I),
    re.compile(r"(24|twenty[\s-]*four)\s*[kK]\s*-?\s*thirty\s*[\s-]*seventy[\s-]*four", re.I),
    # English/digits: 24K3074, 24K-3074, 24 K 3074
    re.compile(r"24\s*[kK]\s*-?\s*3\s*0\s*7\s*4"),
    # Urdu: 24کے + 3074 (with/without spaces or hyphen)
    re.compile(r"24\s*کے\s*-?\s*3\s*0\s*7\s*4"),
    re.compile(r"24\s*کے\s*-?\s*30\s*74"),
    re.compile(r"24\s*کے\s*-?\s*30\s*7"),
    # Urdu spoken digits: تھری زیرو سیون فور
    re.compile(r"24\s*کے\s*-?\s*تھری\s*زیرو\s*سیون\s*فور"),
    re.compile(r"24\s*کے\s*-?\s*تھری\s*زیرو\s*سیون"),
    # Fragment: just 3074
    re.compile(r"3\s*0\s*7\s*4"),
]


def _is_growing(new, old):
    if not old or len(new) <= len(old):
        return False
    check = min(20, len(old))
    return new[:check] == old[:check]


class AttendanceDetector:
    def __init__(self, config):
        self.student       = config["student"]
        # names edited in Dashboard → Settings are used in addition to NAME_EXACT
        self._extra_names  = [n.lower() for n in self.student.get("urdu_names", []) if n and n.strip()]
        self._prev         = ""
        self._att_on       = False
        self._att_time     = 0.0       # when attendance trigger was set
        self._att_timeout  = 300       # 5 minutes to find name
        self._mic_sent     = False
        self._present_sent = False

    def add_caption(self, text):
        pass  # no-op, logic in analyze

    def analyze(self, caption_text):
        if caption_text == self._prev:
            return "nothing"

        prev       = self._prev
        self._prev = caption_text
        growing    = _is_growing(caption_text, prev)
        delta      = caption_text[len(prev):] if growing else caption_text

        # Reset mic on new caption block (new speaker/topic)
        if not growing and not self._att_on:
            self._mic_sent = False

        att  = self._is_att(delta)
        name = self._is_name(delta)

        logger.info(
            f"[Detector] delta='{delta[-60:]}' "
            f"att={att} name={name} "
            f"att_on={self._att_on} mic={self._mic_sent} present={self._present_sent}"
        )

        # Present already sent — only mic kharab for questions, ignore att
        if self._present_sent:
            if att:
                logger.debug("[Detector] Att seen but present already sent — ignoring")
                return "nothing"
            if name and not self._mic_sent:
                self._mic_sent = True
                time.sleep(1.5)
                logger.info("[Detector] Post-present question → Mic kharab hai")
                return "question_asked"
            return "nothing"

        # Attendance trigger
        if att and not self._att_on:
            self._att_on   = True
            self._att_time = time.time()
            self._mic_sent = False
            logger.info("[Detector] ✓ Attendance triggered — watching for name (5 min)")
            if name:
                self._att_on       = False
                self._att_time     = 0.0
                self._present_sent = True
                time.sleep(1)
                logger.info("[Detector] ✓ PRESENT (att+name together)")
                return "mark_present"
            return "nothing"

        # Waiting for name — check timeout
        if self._att_on:
            elapsed = time.time() - self._att_time
            if elapsed > self._att_timeout:
                logger.info(f"[Detector] ✗ 5min timeout — no name found, resetting")
                self._att_on   = False
                self._att_time = 0.0
                self._mic_sent = False  # allow mic kharab again after timeout

        if self._att_on and name:
            self._att_on       = False
            self._att_time     = 0.0
            self._present_sent = True
            time.sleep(0.3)
            logger.info("[Detector] ✓ PRESENT (name after att)")
            return "mark_present"

        # Name only → mic kharab
        if name and not self._att_on:
            if not self._mic_sent:
                self._mic_sent = True
                time.sleep(1)
                logger.info("[Detector] Mic kharab hai")
                return "question_asked"
            return "nothing"

        return "nothing"

    def reset(self):
        self._att_on       = False
        self._att_time     = 0.0       # when attendance trigger was set
        self._att_timeout  = 420       # 5 minutes to find name
        self._mic_sent     = False
        self._present_sent = False
        self._prev         = ""

    def _is_att(self, text):
        t = text.lower()
        return any(p.lower() in t for p in ATTENDANCE_EXACT)

    def _is_name(self, text):
        t = text.lower()
        if any(n.lower() in t for n in NAME_EXACT):
            return True
        if any(n in t for n in self._extra_names):
            return True
        return any(p.search(text) for p in ROLL_PATTERNS)