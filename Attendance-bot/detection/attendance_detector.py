"""
Attendance Detector - Delta-based. Fully debugged.
"""

import re
from difflib import SequenceMatcher

from core.logger import setup_logger
from utils.lang_utils import normalize_urdu
from detection import addressing

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
    # Devanagari (speech-to-text sometimes writes Urdu this way)
    "साद नईम", "सआद नईम", "सद नईम", "साद नइम", "साद नाईम",
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
    # Speech-to-text garbles the roll number with stray dots/commas/dashes/spaces and writes the
    # "K" in Urdu (کے / کی) or Devanagari (के): "24K 30.74", "24 k 3,074", "24 के 3074", "24-K-3-0-7-4"
    re.compile(r"(?<!\w)24[\s.,\-]*(?:[kK]|کے|کی|के|کا|के)[\s.,\-]*3[\s.,\-]*0[\s.,\-]*7[\s.,\-]*4(?!\d)"),
]


# ── attendance keywords in every way a teacher (or speech-to-text) might say / write them ──────────
_ATT_WORD_RE = re.compile(
    r"(?<!\w)(?:attendance|attendence|atendance|roll\s*call|hazri|haziri|hajri|hazree)(?!\w)", re.I)
_ATT_NON_ASCII = [normalize_urdu(p) for p in ATTENDANCE_EXACT if not p.isascii()] + [
    normalize_urdu(w) for w in ("حاضری", "حاضری لگا", "حاضری لگوا")]
_ATT_DEVANAGARI = ("अटेंडेंस", "अटेन्डेंस", "अटैंडेंस", "अटेंडन्स", "हाज़िरी", "हाजिरी", "हाज़री")

# Does the sentence ask something? ("24K3074 what is a graph" is a question, "24K3074" alone is a roll call.)
_QUESTIONISH = re.compile(
    r"[?\u061f]|(?<!\w)(?:what|why|how|when|where|which|who|explain|tell|define|answer|can\s+you|could\s+you|"
    r"kya|kia|kyun|kyon|kaise|kese|kaisay|batao|bataiye|bataen|samjhao|"
    + "|".join(re.escape(normalize_urdu(w)) for w in ("کیا", "کیوں", "کیسے", "بتائیں", "بتائیے", "بتاؤ", "بتاو", "سمجھائیں"))
    + r"|क्या|क्यों|कैसे|बताओ|बताइए|समझाओ)(?!\w)", re.I)


def looks_like_question(text) -> bool:
    return bool(_QUESTIONISH.search(normalize_urdu(text).casefold()))


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

    @staticmethod
    def is_attendance_keyword(text) -> bool:
        """The teacher is taking attendance ("attendance", "roll call", "حاضری", "अटेंडेंस", "hazri"...)."""
        text = str(text or "")
        folded = normalize_urdu(text).casefold()
        return bool(_ATT_WORD_RE.search(text)
                    or any(phrase and phrase in folded for phrase in _ATT_NON_ASCII)
                    or any(word in text for word in _ATT_DEVANAGARI))

    def _is_att(self, text):
        if self.is_attendance_keyword(text):
            return True
        # My roll number said on its own is a roll call; said inside a question it is not, and
        # neither is "24K3074 gave a good answer" (someone talking ABOUT me).
        spans = [(m.start(), m.end()) for pattern in ROLL_PATTERNS for m in pattern.finditer(text)]
        if not spans or looks_like_question(text):
            return False
        verdict = addressing.classify(text, spans)
        about_me = verdict.role == addressing.REFERENCE and verdict.reason.startswith(("third-person '", "possessive"))
        return not about_me

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

    @staticmethod
    def _has_urdu_script(text):
        return bool(re.search(r"[\u0600-\u06FF\u0900-\u097F]", text))

    def _urdu_full_name_heard(self, text, names):
        """Match full names written in Urdu script, tolerating speech-to-text spelling variants
        (different yeh/heh/kaf/alef forms, diacritics) and one slightly garbled word.
        A different second name (e.g. another student called Saad) must NOT match."""
        norm = normalize_urdu(text)
        tokens = norm.split()
        for name in names:
            if not self._has_urdu_script(name):
                continue
            target = normalize_urdu(name)
            parts = target.split()
            if len(parts) < 2:
                continue
            if target in norm:
                return True
            size = len(parts)
            for i in range(len(tokens) - size + 1):
                window = tokens[i:i + size]
                if (SequenceMatcher(None, " ".join(window), target).ratio() >= 0.86
                        and all(SequenceMatcher(None, w, p).ratio() >= 0.65 for w, p in zip(window, parts))):
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
        if self._urdu_full_name_heard(text, full_names):
            return True
        if self.student.get("respond_to_first_name"):
            first = [n for n in (*NAME_EXACT, *self._extra_names) if n and len(n.split()) == 1]
            return any(re.search(rf"(?<!\w){re.escape(n.casefold())}(?!\w)", t) for n in first)
        return False

    def _configured_full_names(self):
        return [n for n in (*NAME_EXACT, *self._extra_names, str(self.student.get("name", "")).lower())
                if n and len(n.split()) >= 2]

    def _urdu_full_name_spans(self, text, names):
        """Character spans of full names written in Urdu/Devanagari (same fuzzy rule as _urdu_full_name_heard)."""
        spans = []
        pieces = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        folded = [normalize_urdu(p[0]) for p in pieces]
        for name in names:
            if not self._has_urdu_script(name):
                continue
            target = normalize_urdu(name)
            parts = target.split()
            size = len(parts)
            if size < 2:
                continue
            for i in range(len(pieces) - size + 1):
                window = folded[i:i + size]
                joined = " ".join(window)
                close = (SequenceMatcher(None, joined, target).ratio() >= 0.86
                         and all(SequenceMatcher(None, w, p).ratio() >= 0.65 for w, p in zip(window, parts)))
                if joined == target or close:
                    spans.append((pieces[i][1], pieces[i + size - 1][2]))
        return spans

    def mention_spans(self, text):
        """[(start, end)] of every place `text` calls ME: my full name or my roll number (and my first
        name only when student.respond_to_first_name is on). Same rules as is_addressed(), with positions."""
        text = str(text or "")
        spans = [(m.start(), m.end()) for pattern in ROLL_ADDRESS_PATTERNS for m in pattern.finditer(text)]
        spans += [(m.start(), m.end()) for m in FULL_NAME_RE.finditer(text)]
        full_names = self._configured_full_names()
        for name in full_names:
            flexible = r"\s+".join(re.escape(part) for part in name.split())
            spans += [(m.start(), m.end()) for m in re.finditer(flexible, text, re.IGNORECASE)]
        spans += self._urdu_full_name_spans(text, full_names)
        if self.student.get("respond_to_first_name"):
            for name in (*NAME_EXACT, *self._extra_names):
                if name and len(name.split()) == 1:
                    spans += [(m.start(), m.end())
                              for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE)]
        return addressing.merge_spans(text, spans)

    def mention_verdict(self, text):
        """addressing.Verdict: is ME being spoken to, spoken about, or is it unclear?"""
        spans = self.mention_spans(text)
        if not spans:
            return addressing.Verdict(addressing.ADDRESS if self.is_addressed(text) else addressing.NONE,
                                      "no position information")
        return addressing.classify(str(text or ""), spans)

    @staticmethod
    def is_roll_mentioned(text):
        return any(pattern.search(str(text or "")) for pattern in ROLL_ADDRESS_PATTERNS)