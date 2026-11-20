"""
Language helpers so the bot can follow a teacher who speaks Urdu, English or a mix.

* detect_language()  -> "urdu" | "roman_urdu" | "english"
* normalize_urdu()   -> folds the many spellings speech-to-text produces for the same
                        Urdu word, so cue words and names match reliably.
* reply_style()      -> instruction telling the AI which language/script to answer in.
"""

import re
import unicodedata

# Urdu script, plus Devanagari: Whisper often writes Urdu speech in Devanagari (labelled "Hindi")
_ARABIC_LETTER = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u0900-\u097F]")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z']*")

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_FOLD = str.maketrans({
    "\u064A": "\u06CC",  # Arabic yeh -> Farsi/Urdu yeh
    "\u0649": "\u06CC",  # alef maksura
    "\u06D0": "\u06CC",
    "\u06D2": "\u06CC",  # bari yeh -> yeh  (kaise / kaisi spell the same after folding)
    "\u06D3": "\u06CC",
    "\u0643": "\u06A9",  # Arabic kaf -> keheh
    "\u06AA": "\u06A9",
    "\u0647": "\u06C1",  # heh -> heh goal
    "\u06BE": "\u06C1",  # do-chashmi heh -> heh goal
    "\u06C3": "\u06C1",
    "\u06C2": "\u06C1",
    "\u0622": "\u0627",  # alef madda -> alef
    "\u0623": "\u0627",
    "\u0625": "\u0627",
    "\u0624": "\u0648",
    "\u06C0": "\u06C1",
    "\u06BA": "\u0646",  # noon ghunna -> noon
})
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_urdu(text) -> str:
    """Fold Urdu spelling variants, drop diacritics, unify digits and whitespace."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = _DIACRITICS.sub("", text).translate(_FOLD).translate(_ARABIC_DIGITS)
    return " ".join(text.split())


# Common Roman-Urdu words. English look-alikes (is, me, to, hi, do, main, us, so...) are left
# out on purpose so plain English is never mistaken for Roman Urdu.
ROMAN_URDU_WORDS = frozenset("""
tum tu aap ap ho hain hai hon hun hoon tha thi hota hoti hote hoga hogi honge
kya kia kiya kyun kyon kyu kaise kaisay kese kesay kaisa kaisi kesa kesi kab kahan kahaan
kaun kon konsa kaunsa kitna kitni kitne kis kisne kisko kidhar
mein mai meri mera mere hum humein hamara hamari tumhara tumhari aapka aapki apka apki
yeh ye woh wo iska iski isko uska uski usko inka unka
nahi nahin nai haan han ji jee acha achha theek thik shukriya meherbani
batao batayen bataiye bataen bataiye samjhao samjhaiye samjhain samjhen samjha samajh
karo kro karen kren kijiye kijiey kar kia kiye kare karna karta karti karte karein
bolo bolen boliye suno sunao sunen dekho dekhen dekhiye likho likhen
sakta sakti sakte sakta chahiye chahie lekin magar aur bhi agar toh kuch sab bohat bahut
kaam pata abhi ab phir jab tab jo ka ki ke ko se pe par wala wali wale
rahe raha rahi raho baat matlab sawal jawab jawaab
aaj kal pehle phele baad liye lye liya diya dena lena
""".split())


def _letter_counts(text: str):
    arabic = len(_ARABIC_LETTER.findall(text))
    latin = sum(len(w) for w in _LATIN_WORD.findall(text))
    return arabic, latin


def detect_language(text) -> str:
    """Return 'urdu' (Urdu script, possibly with English terms), 'roman_urdu' (Urdu in Latin
    letters, possibly with English terms) or 'english'."""
    text = str(text or "")
    arabic, latin = _letter_counts(text)
    if arabic and arabic >= latin * 0.35:
        return "urdu"
    words = [w.lower().strip("'") for w in _LATIN_WORD.findall(text)]
    if not words:
        return "urdu" if arabic else "english"
    hits = sum(1 for w in words if w in ROMAN_URDU_WORDS)
    if hits >= 2 or (hits >= 1 and hits / len(words) >= 0.3):
        return "roman_urdu"
    return "urdu" if arabic > latin else "english"


_URDISH = (
    "Reply the way a typical Pakistani Gen-Z student texts in a class chat: casual Roman Urdu "
    "(Urdu written in English letters) naturally mixed with English words, technical terms in "
    "English, no Urdu script. Example of the tone: 'Sir samajh agaya hai, but how would we know "
    "ki hamein yeh karna hai?' or 'Sir NP-hard wo problems hain jin ka koi efficient solution "
    "abhi tak known nahi hai.' Polite ('Sir'), one or two short sentences."
)
_STYLE = {
    "english": "Reply in clear, simple English.",
    "urdish": _URDISH,
    "roman_urdu": _URDISH,
    "urdu": (
        "Reply in natural spoken Urdu written in Urdu script (the way a Pakistani student talks). "
        "Keep technical terms in English where people normally say them in English."
    ),
}
_FORCED = {"English": "english", "Urdu": "urdu", "Roman Urdu": "urdish"}


def reply_language(question, setting="auto") -> str:
    """English question -> English reply. Urdu / Hindi-script / Roman Urdu / mixed question ->
    Urdu+English mix (Roman letters). A fixed reply language chosen in Settings wins."""
    forced = _FORCED.get(str(setting or "").strip())
    if forced:
        return forced
    return "english" if detect_language(question) == "english" else "urdish"


def reply_style(question, setting="auto") -> str:
    return _STYLE[reply_language(question, setting)]
