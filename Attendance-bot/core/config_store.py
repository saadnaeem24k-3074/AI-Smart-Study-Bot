"""
Config store — the single place that reads/writes config/schedule.json.

Used by the dashboard (add/edit/delete classes, settings) and by the
scheduler (hot-reload + removing one-off "quick join" classes).
Writes are atomic and guarded by a process-wide lock.
"""

import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv, set_key, unset_key

CONFIG_PATH = Path("config/schedule.json")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH, override=False)
PKT = ZoneInfo("Asia/Karachi")
_LOCK = threading.RLock()

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DEFAULT_FEATURES = {
    "notes": True,            # save lecture transcript to notes/
    "ai_summary": True,       # LLM summary at class end (needs API key)
    "called_alert": True,     # sound + popup when your name is called
    "slides": True,           # capture slides + build PDF with notes
    "whisper_transcription": True,  # local transcription of meeting playback for lecture notes
    "slide_mode": "auto",     # auto | always | off
    "slide_interval": 4,      # seconds between slide checks
    "keyframe_interval": 30,  # snapshot every N sec while the screen is a video/whiteboard (0 = off)
    "caption_language": "urdu",   # urdu | english | keep (leave Meet's own setting alone)
    "notes_language": "English",  # language of AI summaries: English | Urdu | Roman Urdu
    "pdf_detail": "detailed",  # concise | detailed
    "pdf_include_transcript": False,  # full captions are also saved separately in transcript.md
    "pdf_paper_size": "A4",  # A4 | Letter
}
PROVIDERS = {
    "anthropic": {"label": "Anthropic (Claude)", "model": "claude-sonnet-5-5", "env": "ANTHROPIC_API_KEY"},
    "deepseek":  {"label": "DeepSeek",           "model": "deepseek-chat",     "env": "DEEPSEEK_API_KEY"},
    "gemini":    {"label": "Google Gemini",      "model": "gemini-2.5-flash",  "env": "GEMINI_API_KEY"},
}
MIN_PARTICIPANTS_DEFAULT = 6
CAPTION_LANGS = ("urdu", "english", "keep")
NOTES_LANGS = ("English", "Urdu", "Roman Urdu")


# ───────────────────────── raw read / write ─────────────────────────
def load_raw() -> Dict:
    with _LOCK:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def save_raw(cfg: Dict) -> None:
    with _LOCK:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)


def mtime() -> float:
    try:
        return CONFIG_PATH.stat().st_mtime
    except OSError:
        return 0.0


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def ensure_ids() -> Dict:
    """Give every class a stable id (persisted) and return the config."""
    with _LOCK:
        cfg = load_raw()
        changed = False
        for c in cfg.get("classes", []):
            if not c.get("id"):
                c["id"] = new_id()
                changed = True
        if changed:
            save_raw(cfg)
        return cfg


# ───────────────────────── features / settings ─────────────────────────
def get_features(cfg: Dict) -> Dict:
    f = dict(DEFAULT_FEATURES)
    f.update(cfg.get("features") or {})
    return f


def get_ai(cfg: Dict) -> Dict:
    """→ {provider, keys{provider: key}, models{provider: model}} (old single-key format is migrated)."""
    a = cfg.get("ai") or {}
    prov = a.get("provider") if a.get("provider") in PROVIDERS else "anthropic"
    keys = dict(a.get("keys") or {})
    models = dict(a.get("models") or {})
    if a.get("api_key") and not keys.get("anthropic"):
        keys["anthropic"] = a["api_key"]
    if str(a.get("model", "")).startswith("claude") and not models.get("anthropic"):
        models["anthropic"] = a["model"]
    return {"provider": prov, "keys": keys, "models": models}


def ai_provider(cfg: Dict) -> str:
    return get_ai(cfg)["provider"]


def ai_key(cfg: Dict, provider: Optional[str] = None) -> str:
    ai = get_ai(cfg)
    prov = provider or ai["provider"]
    return (os.environ.get(PROVIDERS[prov]["env"], "") or ai["keys"].get(prov) or "").strip()


def ai_model(cfg: Dict, provider: Optional[str] = None) -> str:
    ai = get_ai(cfg)
    prov = provider or ai["provider"]
    return (ai["models"].get(prov) or PROVIDERS[prov]["model"]).strip()


def min_participants(cfg: Dict) -> int:
    try:
        return int((cfg.get("global_settings") or {}).get("min_participants", MIN_PARTICIPANTS_DEFAULT))
    except (TypeError, ValueError):
        return MIN_PARTICIPANTS_DEFAULT


def public_config() -> Dict:
    """Config for the dashboard — never includes the API key itself."""
    cfg = ensure_ids()
    ai = get_ai(cfg)
    providers = {}
    for name, info in PROVIDERS.items():
        key = ai_key(cfg, name)
        providers[name] = {"label": info["label"], "default_model": info["model"],
                           "model": ai["models"].get(name, ""),
                           "has_key": bool(key), "key_hint": ("…" + key[-4:]) if key else ""}
    classes = sorted(
        cfg.get("classes", []),
        key=lambda c: (DAY_ORDER.index(c["day"]) if c.get("day") in DAY_ORDER else 9, c.get("time", "")),
    )
    return {
        "student": cfg.get("student", {}),
        "classes": classes,
        "settings": {"min_participants": min_participants(cfg)},
        "features": get_features(cfg),
        "ai": {"provider": ai["provider"], "providers": providers},
    }


def update_settings(data: Dict) -> None:
    with _LOCK:
        cfg = load_raw()

        st = data.get("student")
        if isinstance(st, dict):
            cur = cfg.setdefault("student", {})
            if "name" in st:
                cur["name"] = str(st["name"]).strip()
            if "roll_no" in st:
                cur["roll_no"] = str(st["roll_no"]).strip()
            if "urdu_names" in st:
                names = st["urdu_names"]
                if isinstance(names, str):
                    names = names.splitlines()
                cur["urdu_names"] = [n.strip() for n in names if n and n.strip()]

        s = data.get("settings")
        if isinstance(s, dict) and "min_participants" in s:
            mp = int(s["min_participants"])
            if not 0 <= mp <= 500:
                raise ValueError("Minimum participants must be 0–500")
            cfg.setdefault("global_settings", {})["min_participants"] = mp

        ft = data.get("features")
        if isinstance(ft, dict):
            cur = cfg.setdefault("features", {})
            for k in ("notes", "ai_summary", "called_alert", "slides", "whisper_transcription"):
                if k in ft:
                    cur[k] = bool(ft[k])
            if "slide_mode" in ft:
                if ft["slide_mode"] not in ("auto", "always", "off"):
                    raise ValueError("Slide mode must be auto, always or off")
                cur["slide_mode"] = ft["slide_mode"]
            if "caption_language" in ft:
                if ft["caption_language"] not in CAPTION_LANGS:
                    raise ValueError("Caption language must be urdu, english or keep")
                cur["caption_language"] = ft["caption_language"]
            if "notes_language" in ft:
                if ft["notes_language"] not in NOTES_LANGS:
                    raise ValueError("Notes language must be English, Urdu or Roman Urdu")
                cur["notes_language"] = ft["notes_language"]
            if "pdf_detail" in ft:
                if ft["pdf_detail"] not in ("concise", "detailed"):
                    raise ValueError("PDF note detail must be concise or detailed")
                cur["pdf_detail"] = ft["pdf_detail"]
            if "pdf_include_transcript" in ft:
                cur["pdf_include_transcript"] = bool(ft["pdf_include_transcript"])
            if "pdf_paper_size" in ft:
                if ft["pdf_paper_size"] not in ("A4", "Letter"):
                    raise ValueError("PDF paper size must be A4 or Letter")
                cur["pdf_paper_size"] = ft["pdf_paper_size"]
            if "keyframe_interval" in ft:
                kf = int(ft["keyframe_interval"])
                if kf != 0 and not 10 <= kf <= 300:
                    raise ValueError("Snapshot interval must be 0 (off) or 10–300 seconds")
                cur["keyframe_interval"] = kf
            if "slide_interval" in ft:
                iv = int(ft["slide_interval"])
                if not 2 <= iv <= 60:
                    raise ValueError("Slide interval must be 2–60 seconds")
                cur["slide_interval"] = iv

        ai = data.get("ai")
        if isinstance(ai, dict):
            cur = get_ai(cfg)
            prov = ai.get("provider") or cur["provider"]
            if prov not in PROVIDERS:
                raise ValueError("Provider must be anthropic, deepseek or gemini")
            keys, models = cur["keys"], cur["models"]
            env_name = PROVIDERS[prov]["env"]
            if ai.get("clear_key"):
                keys.pop(prov, None)
                if ENV_PATH.exists():
                    unset_key(str(ENV_PATH), env_name)
                os.environ.pop(env_name, None)
            elif ai.get("api_key"):          # empty string = keep existing key
                key = str(ai["api_key"]).strip()
                if key:
                    set_key(str(ENV_PATH), env_name, key, quote_mode="always")
                    os.environ[env_name] = key
                    keys.pop(prov, None)
            if "model" in ai:
                m = str(ai["model"] or "").strip()
                if m:
                    models[prov] = m
                else:
                    models.pop(prov, None)
            cfg["ai"] = {"provider": prov, "keys": keys, "models": models}

        save_raw(cfg)


# ───────────────────────── classes ─────────────────────────
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def validate_class(data: Dict) -> Dict:
    day = str(data.get("day", "")).strip().capitalize()
    if day not in DAY_ORDER:
        raise ValueError("Day must be Monday–Sunday")
    time_s = str(data.get("time", "")).strip()
    if not _TIME_RE.match(time_s):
        raise ValueError("Time must be HH:MM (24-hour)")
    h, m = time_s.split(":")
    time_s = f"{int(h):02d}:{m}"
    try:
        duration = int(data.get("duration"))
    except (TypeError, ValueError):
        raise ValueError("Duration must be a number of minutes")
    if not 1 <= duration <= 600:
        raise ValueError("Duration must be 1–600 minutes")
    subject = str(data.get("subject", "")).strip()
    if not subject:
        raise ValueError("Subject is required")
    platform = str(data.get("platform", "meet")).strip().lower()
    if platform not in ("meet", "zoom"):
        raise ValueError("Platform must be meet or zoom")
    link = str(data.get("link", "")).strip()
    if link and not re.match(r"^https?://", link):
        raise ValueError("Link must start with http:// or https://")
    out = {"day": day, "time": time_s, "duration": duration,
           "subject": subject, "platform": platform, "link": link}
    if "captions" in data:                       # optional per-class caption language
        cap = str(data.get("captions") or "").strip().lower()
        if cap and cap not in CAPTION_LANGS:
            raise ValueError("Captions must be urdu, english or keep")
        if cap:
            out["captions"] = cap
    return out


def add_class(data: Dict, once: bool = False) -> Dict:
    c = validate_class(data)
    c["id"] = new_id()
    if once:
        c["once"] = True
    with _LOCK:
        cfg = load_raw()
        cfg.setdefault("classes", []).append(c)
        save_raw(cfg)
    return c


def update_class(cid: str, data: Dict) -> Dict:
    c = validate_class(data)
    with _LOCK:
        cfg = load_raw()
        for i, old in enumerate(cfg.get("classes", [])):
            if old.get("id") == cid:
                c["id"] = cid
                for k in ("_test", "once"):       # keep flags
                    if old.get(k):
                        c[k] = old[k]
                if "captions" not in data and old.get("captions"):
                    c["captions"] = old["captions"]
                cfg["classes"][i] = c
                save_raw(cfg)
                return c
    raise KeyError("Class not found")


def delete_class(cid: str) -> bool:
    with _LOCK:
        cfg = load_raw()
        before = len(cfg.get("classes", []))
        cfg["classes"] = [c for c in cfg.get("classes", []) if c.get("id") != cid]
        if len(cfg["classes"]) == before:
            return False
        save_raw(cfg)
        return True


def quick_join(link: str, subject: str, duration: int, platform: Optional[str] = None) -> Dict:
    """One-off class starting 'now' (backdated 3 min so the scheduler joins immediately)."""
    link = (link or "").strip()
    if not link:
        raise ValueError("Paste a meeting link")
    if platform is None:
        platform = "zoom" if "zoom.us" in link else "meet"
    now = datetime.now(PKT) - timedelta(minutes=3)
    return add_class({
        "day": now.strftime("%A"), "time": now.strftime("%H:%M"),
        "duration": int(duration) + 3,
        "subject": (subject or "Quick join").strip(),
        "platform": platform, "link": link,
    }, once=True)
