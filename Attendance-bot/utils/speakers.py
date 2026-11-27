"""
Who is talking?

Meet's live captions label every caption block with the speaker's display name, but local Whisper
audio has no speaker information at all. SpeakerTracker keeps a short timeline of "this person's
caption just grew", which gives us two things:

  * a roster of participant names (used to tell "Ali, what is NP?" apart from a question for me);
  * the most likely speaker for a piece of Whisper audio, taken from whoever's captions were
    moving at that moment. When two people overlap, or nobody's captions moved, the answer is ""
    (unknown) rather than a guess - a wrong label is worse than no label.
"""

import time
from collections import deque
from typing import Dict, Iterable, List, Optional

UNKNOWN = ""
SELF_LABELS = {"you", "me", "myself"}
_IGNORED = {"", "unknown", "unattributed", "local audio (whisper)"}


def _key(name: str) -> str:
    return " ".join(str(name or "").split()).casefold()


class SpeakerTracker:
    def __init__(self, self_names: Iterable[str] = ()):
        self.self_keys = {_key(n) for n in self_names if n} | SELF_LABELS
        self.roster: Dict[str, Dict] = {}
        self._events = deque(maxlen=600)          # (timestamp, speaker)

    # ── feeding ──────────────────────────────────────────
    def observe(self, speaker: str, now: Optional[float] = None, words: int = 1) -> None:
        """A caption block labelled `speaker` just grew by `words` words."""
        name = " ".join(str(speaker or "").split())
        if _key(name) in _IGNORED:
            return
        now = time.time() if now is None else now
        info = self.roster.setdefault(name, {"first": now, "last": now, "turns": 0, "words": 0})
        info["last"] = now
        info["words"] += max(0, words)
        self._events.append((now, name))

    def new_turn(self, speaker: str) -> None:
        info = self.roster.get(" ".join(str(speaker or "").split()))
        if info:
            info["turns"] += 1

    # ── questions ────────────────────────────────────────
    def is_self(self, speaker: str) -> bool:
        return _key(speaker) in self.self_keys

    def names(self, include_self: bool = False) -> List[str]:
        return [n for n in self.roster if include_self or not self.is_self(n)]

    def active_speaker(self, now: Optional[float] = None, window: float = 8.0,
                       min_share: float = 0.6) -> str:
        """Speaker whose captions moved most in the last `window` seconds, or "" when it is unclear."""
        now = time.time() if now is None else now
        counts: Dict[str, int] = {}
        for stamp, name in self._events:
            if now - window <= stamp <= now + 1.0:
                counts[name] = counts.get(name, 0) + 1
        if not counts:
            return UNKNOWN
        total = sum(counts.values())
        name, hits = max(counts.items(), key=lambda item: item[1])
        return name if hits / total >= min_share else UNKNOWN

    def stats(self) -> List[Dict]:
        return sorted(
            ({"speaker": n, **{k: v for k, v in info.items() if k in ("turns", "words")}}
             for n, info in self.roster.items()),
            key=lambda row: -row["words"],
        )
