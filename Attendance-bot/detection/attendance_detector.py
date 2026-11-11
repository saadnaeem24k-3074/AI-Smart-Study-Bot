"""
Attendance Detector - Delta-based. Fully debugged.
"""

import re
from core.logger import setup_logger

logger = setup_logger("AttendanceDetector")

ATTENDANCE_EXACT = [
    "اٹینڈنس", "ٹینڈنس", "اٹینڈینس",
    "اٹندڈن", "ٹندڈنس", "اٹندڈنس",
    "اٹینڈنس مارک", "اٹینڈنس مارک کروا لیں",
    "اٹینڈنس مارک کر رہا ہوں", "اٹینڈنس مارک کر رہی ہوں",
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
    re.compile(r"(?<!\w)(24|twenty[\s-]*four)\s*[kK]\s*-?\s*(three|3)\s*(zero|oh|0)\s*(seven|7)\s*(four|4)(?!\w)", re.I),
    re.compile(r"(?<!\w)(24|twenty[\s-]*four)\s*[kK]\s*-?\s*thirty\s*[\s-]*seventy[\s-]*four(?!\w)", re.I),
    # English/digits: 24K3074, 24K-3074, 24 K 3074
    re.compile(r"(?<!\w)24\s*[kK]\s*-?\s*3\s*0\s*7\s*4(?!\w)"),
    # Urdu: 24کے + 3074 (with/without spaces or hyphen)
    re.compile(r"(?<!\w)24\s*کے\s*-?\s*3\s*0\s*7\s*4(?!\w)"),
    re.compile(r"(?<!\w)24\s*کے\s*-?\s*30\s*74(?!\w)"),
    # Urdu spoken digits: تھری زیرو سیون فور
    re.compile(r"(?<!\w)24\s*کے\s*-?\s*تھری\s*زیرو\s*سیون\s*فور(?!\w)"),
]

ROLL_ADDRESS_PATTERNS = [
    *ROLL_PATTERNS,
    re.compile(r"(?<!\w)24\s*[kK][\s-]*3[\s-]*0\s*7\s*4(?!\w)"),
]


# English STT spellings of the full name ("Saad Naeem", "Sad Naim", "Saat Nayeem" ...)
FULL_NAME_RE = re.compile(
    r"(?<!\w)sa+[dt]\s+(?:na+[iy]?e*[mn]|nayeem|naeim|na\W?im|nayim|neem|nayem)(?!\w)", re.I)


class AttendanceDetector:
    def __init__(self, config):
        self.student       = config["student"]
        # names edited in Dashboard → Settings are used in addition to NAME_EXACT
        self._extra_names  = [n.lower() for n in self.student.get("urdu_names", []) if n and n.strip()]
        self._prev         = ""
        self._present_sent = False

    def add_caption(self, text):
        pass  # no-op, logic in analyze

    def analyze(self, caption_text):
        if caption_text == self._prev:
            return "nothing"

        self._prev = caption_text
        if self._present_sent:
            return "nothing"
        if self._is_att(caption_text):
            self._present_sent = True
            logger.info("[Detector] Attendance keyword or roll number detected")
            return "mark_present"
        return "nothing"

    def reset(self):
        self._present_sent = False
        self._prev         = ""

    def _is_att(self, text):
        t = text.casefold()
        attendance_word = re.search(r"(?<!\w)attendance(?!\w)", t)
        attendance_variant = any(
            phrase in t for phrase in ATTENDANCE_EXACT if not phrase.isascii()
        )
        return bool(attendance_word or attendance_variant
                    or any(pattern.search(text) for pattern in ROLL_PATTERNS))

    def is_name_mentioned(self, text):
        t = text.casefold()
        for name in [*NAME_EXACT, *self._extra_names]:
            name = name.casefold().strip()
            if not name:
                continue
            if name.isascii():
                if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", t):
                    return True
            elif name in t:
                return True
        return False

    def is_addressed(self, text):
        """True only when the teacher calls ME: full name or roll number.

        A bare first name ("Saad") is ignored by default because other students may share it;
        set student.respond_to_first_name = true in schedule.json to also accept it.
        """
        text = str(text or "")
        if self.is_roll_mentioned(text):
            return True
        if FULL_NAME_RE.search(text):
            return True
        t = text.casefold()
        full_names = [n for n in (*NAME_EXACT, *self._extra_names, str(self.student.get("name", "")).lower())
                      if n and len(n.split()) >= 2]
        if any(" ".join(n.casefold().split()) in " ".join(t.split()) for n in full_names):
            return True
        if self.student.get("respond_to_first_name"):
            first = [n for n in (*NAME_EXACT, *self._extra_names) if n and len(n.split()) == 1]
            return any(re.search(rf"(?<!\w){re.escape(n.casefold())}(?!\w)", t) for n in first)
        return False

    @staticmethod
    def is_roll_mentioned(text):
        return any(pattern.search(str(text or "")) for pattern in ROLL_ADDRESS_PATTERNS)