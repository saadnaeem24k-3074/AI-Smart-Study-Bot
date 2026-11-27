"""
Addressing "brain" - decides WHAT a mention of my name / roll number means.

    "Saad Naeem, what is an NP problem?"         -> address    (someone is asking ME)
    "Saad Naeem gave a good answer"              -> reference  (talking ABOUT me - stay silent)
    "Did 24K-3074 submit the assignment?"        -> reference
    "I think Saad Naeem what is NP is tricky"    -> ambiguous  (let the AI judge with context)

It also decides whether a later sentence is a genuine follow-up to a conversation I was pulled
into, or a question meant for somebody else. Everything here is pure Python (no network), so it
is fast, deterministic and unit-tested. The AI judge in utils/ai_notes.py is only consulted for
the genuinely ambiguous cases, and it fails closed: when in doubt the bot stays silent.
"""

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from utils.lang_utils import normalize_urdu

ADDRESS = "address"        # I am being spoken TO
REFERENCE = "reference"    # I am being spoken ABOUT
AMBIGUOUS = "ambiguous"    # cannot tell from the words alone
NONE = "none"              # no mention of me

Span = Tuple[int, int]


def _fold(word: str) -> str:
    return normalize_urdu(str(word or "")).casefold()


def _fold_set(*groups: str) -> frozenset:
    words = set()
    for group in groups:
        for word in group.split():
            words.add(_fold(word))
    return frozenset(words)


# ── vocabulary (English, Roman Urdu, Urdu script, Devanagari) ─────────────────────────────────
# Words that, right AFTER my name, mean someone is talking ABOUT me ("Saad Naeem gave ...").
_REF_AFTER = _fold_set(
    "gave gives give said says answered answers did does didn't doesn't got gets wrote writes told "
    "asked asks mentioned explained explains replied replies solved solves scored passed failed came "
    "comes went goes knows thinks thought made makes joined left was were has had hasn't isn't "
    "wasn't won lost helped shared presented sent submitted completed finished done absent late "
    "kaha kehte bola bataya diya dia kiya tha thi aya aaya gaya mila ne ka ki ke ko",
    "کہا بولا بتایا دیا تھا تھی آیا گیا نے کا کی کے کو",
    "ने का की के को",
)
# Words after my name that could be either ("Saad Naeem is ..." / Roman-Urdu "is" = "this").
_AMBIGUOUS_AFTER = _fold_set("is are can could will would should may might must also too")
# Words right BEFORE my name that put me in the third person ("thanks to Saad Naeem",
# "did Saad Naeem answer", "ask Saad Naeem").
_REF_BEFORE = _fold_set(
    "thanks thank ask tell told asked call called by from about for of like than with to that because "
    "see look invite did does is was has had will can could would should are were do have if whether "
    "where who whom whose says said according credit",
    "شکریہ سے کے کا کی",
    "से के का की",
)
# Words at the start of a sentence that do not stop a name from being a call-on.
_START_FILLERS = _fold_set(
    "hey hi hello ok okay alright so now next well right yes yeah haan han ji sir madam please "
    "chalo acha accha theek thik oye oi listen",
    "اچھا چلو ٹھیک ہاں جی سر",
    "अच्छा चलो ठीक हाँ जी",
)
# Words at the end of a sentence that do not stop a trailing name from being a call-on.
_END_FILLERS = _fold_set("please pls ji sir madam bhai yaar bro answer reply", "جی سر بھائی یار", "जी सर भाई यार")
_YOU = _fold_set(
    "you your yours aap ap tum tumhe tumhein aapko aapka aapki tera tujhe",
    "آپ تم تمہیں آپکو آپ کا",
    "आप तुम आपको",
)
_CONJ = _fold_set("and or aur ya", "اور یا", "और या")

# Continuation cues: a follow-up that clearly refers back to the previous exchange.
_CONTINUATION = re.compile(
    r"^(?:and|also|then|so|but|why|how come|what about|how about|aur|phir|lekin|magar|to|toh|kyun|"
    r"kyon|اور|پھر|لیکن|مگر|اور|और|फिर|लेकिन)\b|"
    r"\b(?:it|its|that|this|those|these|they|them|he|she|iska|uska|iski|uski|isme|usme|ye|yeh|wo|woh|"
    r"یہ|وہ|اس|اسکا|اسکی|ये|वो|इस|उस)\b",
    re.IGNORECASE,
)
# "Ali, what is ..." / "Hey Sara:" - a vocative aimed at somebody else.
_OTHER_VOCATIVE = re.compile(
    r"^\s*(?:(?:hey|hi|hello|ok|okay|so|now|next|acha|accha|oye)[\s,]+)?"
    r"([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\s*[,:]"
)
_WORD = re.compile(r"[^\s,.;:!?\u061f\u060c\u06d4\u0964\"'()\[\]{}\-]+")
_VOCATIVE_PUNCT = ",:;-\u2014\u060c?\u061f"


@dataclass
class Verdict:
    role: str = NONE
    reason: str = ""
    span: Optional[Span] = None


def _words(text: str) -> List[str]:
    return [_fold(w) for w in _WORD.findall(str(text or ""))]


def merge_spans(text: str, spans: Iterable[Span]) -> List[Span]:
    """Merge overlapping spans and spans joined only by 'and / or / aur' ("Saad Naeem or 24K-3074")."""
    ordered = sorted(set((a, b) for a, b in spans if b > a))
    merged: List[Span] = []
    for start, end in ordered:
        if merged:
            prev_start, prev_end = merged[-1]
            gap = text[prev_end:start]
            gap_words = _words(gap)
            if start <= prev_end or (len(gap_words) <= 1 and all(w in _CONJ for w in gap_words)):
                merged[-1] = (prev_start, max(prev_end, end))
                continue
        merged.append((start, end))
    return merged


def classify(text: str, spans: Sequence[Span]) -> Verdict:
    """Decide whether the mention(s) of me in `text` are a call-on, a reference or unclear."""
    text = str(text or "")
    clusters = merge_spans(text, spans)
    if not clusters:
        return Verdict(NONE, "no mention")
    start, end = clusters[0][0], clusters[-1][1]
    before, after = text[:start], text[end:]
    before_words, after_words = _words(before), _words(after)
    next_char = after.lstrip()[:1]
    all_words = _words(text)
    says_you = any(w in _YOU for w in all_words)
    span = (start, end)

    if after.startswith(("'s", "\u2019s")):
        return Verdict(REFERENCE, "possessive", span)
    if before_words and before_words[-1] in _REF_BEFORE:
        return Verdict(REFERENCE, f"third person after '{before_words[-1]}'", span)
    if after_words and after_words[0] in _REF_AFTER and next_char not in _VOCATIVE_PUNCT:
        if says_you:
            return Verdict(AMBIGUOUS, "third-person verb but also 'you'", span)
        return Verdict(REFERENCE, f"third-person '{after_words[0]}' after the name", span)
    if next_char in _VOCATIVE_PUNCT and next_char:
        return Verdict(ADDRESS, "name followed by comma / question", span)
    at_start = all(w in _START_FILLERS for w in before_words)
    at_end = all(w in _END_FILLERS for w in after_words)
    if at_end and not at_start:
        return Verdict(ADDRESS, "name closes the sentence", span)
    if at_start:
        if after_words and after_words[0] in _AMBIGUOUS_AFTER:
            return Verdict(AMBIGUOUS, f"'{after_words[0]}' after the name can be either", span)
        return Verdict(ADDRESS, "name opens the sentence", span)
    return Verdict(AMBIGUOUS, "name in the middle of a sentence", span)


# ── other people ─────────────────────────────────────────────────────────────────────────────
_IGNORED_LABELS = {"", "you", "unknown", "unattributed", "local audio (whisper)"}


def _label_ok(label: str) -> bool:
    low = str(label or "").strip().casefold()
    return bool(low) and low not in _IGNORED_LABELS and not low.startswith("unattributed")


def directed_to_other(sentence: str, roster: Iterable[str], self_names: Iterable[str] = ()) -> bool:
    """True when the sentence opens or closes with somebody ELSE's name ("Ali, what is ..."),
    taking participant names seen in the captions into account."""
    sentence = str(sentence or "")
    mine = {_fold(n) for n in self_names if n}
    mine |= {w for n in self_names for w in _words(n)}
    for label in roster or ():
        if not _label_ok(label) or _fold(label) in mine:
            continue
        pieces = [str(label).strip()] + [p for p in str(label).split() if len(p) >= 3]
        for piece in dict.fromkeys(pieces):
            if _fold(piece) in mine:
                continue
            pattern = rf"(?<!\w){re.escape(piece)}(?!\w)"
            for found in re.finditer(pattern, sentence, re.IGNORECASE):
                verdict = classify(sentence, [(found.start(), found.end())])
                if verdict.role == ADDRESS:
                    return True
    match = _OTHER_VOCATIVE.match(sentence)
    if match and _fold(match.group(1)) not in mine:
        first = _words(match.group(1))
        if not any(w in mine for w in first):
            return True
    return False


def has_continuation_cue(sentence: str) -> bool:
    return bool(_CONTINUATION.search(_fold(sentence)))


def same_speaker(a: str, b: str) -> bool:
    return bool(a) and bool(b) and _fold(a) == _fold(b)


# ── conversation floor ───────────────────────────────────────────────────────────────────────
@dataclass
class Floor:
    """Who I am currently in a conversation with. Follow-ups are only accepted from THAT person."""

    window: float = 20.0
    max_followups: int = 2
    speaker: str = ""
    opened_at: float = 0.0
    followups: int = 0
    open_: bool = field(default=False)

    def open(self, speaker: str, now: float) -> None:
        self.speaker, self.opened_at, self.followups, self.open_ = str(speaker or ""), now, 0, True

    def close(self) -> None:
        self.open_ = False
        self.speaker = ""

    def refresh(self, now: float) -> None:
        self.opened_at = now

    def expired(self, now: float) -> bool:
        return not self.open_ or now - self.opened_at > self.window

    def decide(self, speaker: str, sentence: str, now: float, other_directed: bool) -> str:
        """'accept' | 'maybe' (ask the AI judge) | 'reject' for a question heard while the floor is open."""
        if self.expired(now):
            return "reject"
        if other_directed or self.followups >= self.max_followups:
            return "reject"
        if speaker and self.speaker:
            return "accept" if same_speaker(speaker, self.speaker) else "reject"
        # speaker unknown on one side: only a sentence that clearly points back is a follow-up
        return "accept" if has_continuation_cue(sentence) and len(sentence.split()) <= 14 else "maybe"
