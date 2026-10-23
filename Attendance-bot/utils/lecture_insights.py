"""
Offline lecture analysis — works with NO API key.

* find_flags():   moments where the teacher stressed something (exam / important /
                  assignment-deadline), in English, Urdu and mixed speech.
* top_keywords(): most repeated English terms (technical words usually stay English).
* fmt_dur():      "2m 10s" style durations.
"""

import re
from collections import Counter
from typing import Dict, List

FLAG_RULES = [
    ("EXAM", "Exam / paper", re.compile(
        r"\b(exam|exams|paper|papers|quiz|quizzes|midterm|mid-term|final|finals|marks|test)\b"
        r"|امتحان|پیپر|کوئز|ٹیسٹ|مڈ ?ٹرم|فائنل|نمبر|مارکس", re.I)),
    ("IMPORTANT", "Important", re.compile(
        r"\b(important|remember|note this|note that|key point|focus on|don'?t forget|must know)\b"
        r"|اہم|یاد رکھ|نوٹ کر|دھیان|ضروری|امپورٹنٹ", re.I)),
    ("DEADLINE", "Assignment / deadline", re.compile(
        r"\b(assignment|assignments|homework|submit|submission|deadline|due date|project|lab report)\b"
        r"|اسائنمنٹ|ہوم ?ورک|جمع|ڈیڈ ?لائن|پروجیکٹ|سبمٹ", re.I)),
]

_SENT_SPLIT = re.compile(r"(?<=[.!?۔؟])\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z\-']{3,}")
_STOP = set("""
that this with have from they them then than there their what when where which while will would could should about
after again also been before being between both does doing down each even ever every first from further getting
give going gone good great here into just know like make many more most much must only other over said same
some such take than that them these those through under until very want well were your yeah okay right
because because actually basically something someone thing things think today tomorrow next class lecture
please sir mam madam ahead back called come comes does done kind look looks mean means need needs part really
second still talk talking tell then thing time using used uses want wants ways yeah yes
""".split())


def find_flags(segments, limit: int = 12) -> List[Dict]:
    """segments: objects with .text .ts .slide .speaker → [{kind,label,time,slide,text}]"""
    out, seen = [], set()
    for seg in segments:
        text = seg.text or ""
        for kind, label, rx in FLAG_RULES:
            m = rx.search(text)
            if not m:
                continue
            sent = next((s for s in _SENT_SPLIT.split(text) if rx.search(s)), text)
            sent = " ".join(sent.split())
            if len(sent) > 240:
                a = max(0, sent.lower().find(m.group(0).lower()) - 100)
                sent = ("…" if a else "") + sent[a:a + 240] + "…"
            key = (kind, sent[:60])
            if key in seen:
                continue
            seen.add(key)
            out.append({"kind": kind, "label": label, "time": seg.ts.strftime("%H:%M"),
                        "slide": seg.slide, "text": sent})
            break          # one flag per segment is enough
        if len(out) >= limit:
            break
    return out


def top_keywords(text: str, n: int = 10) -> List[str]:
    words = [w.lower().strip("-'") for w in _WORD.findall(text or "")]
    cnt = Counter(w for w in words if w not in _STOP and len(w) >= 4)
    return [w.capitalize() for w, c in cnt.most_common(n) if c >= 2]


def fmt_dur(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"
