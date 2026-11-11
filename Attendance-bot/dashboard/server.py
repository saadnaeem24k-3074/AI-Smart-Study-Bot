"""
Dashboard server — Flask.

Pages/API:
  /                      single-page UI (Overview · Schedule · Notes · Settings)
  /api/state             live bot state
  /api/config            schedule + settings (API key is never sent back)
  /api/classes           POST add · PUT/DELETE /<id> edit/remove
  /api/quickjoin         join a meeting link right now
  /api/settings          save name/roll/features/AI key
  /api/notes, /notes/..  saved class notes (PDF / transcript)

By default it listens on 127.0.0.1 only (this PC). Set "dashboard": {"host": "0.0.0.0"}
in schedule.json if you want to open it from your phone — but then anyone on your
Wi-Fi can edit your schedule, so only do that on a network you trust.
"""

import json
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from flask_socketio import SocketIO

from core import config_store
from dashboard.page import PAGE
from dashboard import study_page
from utils import ai_notes
from utils.state_store import StateStore

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
state = StateStore()

NOTES_ROOT = Path("notes")


@app.before_request
def _require_json_for_writes():
    # Blocks cross-site form posts: a JSON content-type forces a CORS preflight.
    if request.method in ("POST", "PUT") and not request.is_json:
        return jsonify(error="JSON body required"), 415


@app.errorhandler(ValueError)
def _bad_value(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(KeyError)
def _missing(e):
    return jsonify(error=str(e).strip("'\"")), 404


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _note_directory(folder: str) -> Path:
    root = NOTES_ROOT.resolve()
    target = (root / folder).resolve()
    if root not in target.parents or not (target / "meta.json").is_file():
        abort(404)
    return target


# ───────────────────────── pages ─────────────────────────
@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


# ───────────────────────── state / history ─────────────────────────
@app.get("/api/state")
def api_state():
    return jsonify(state.all())


@app.get("/api/history")
def api_history():
    return jsonify(_load_history()[-20:][::-1])


def _load_history():
    p = Path("logs/attendance_history.json")
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# ───────────────────────── config ─────────────────────────
@app.get("/api/config")
def api_config():
    return jsonify(config_store.public_config())


@app.post("/api/classes")
def api_add_class():
    return jsonify(config_store.add_class(_body())), 201


@app.put("/api/classes/<cid>")
def api_update_class(cid):
    return jsonify(config_store.update_class(cid, _body()))


@app.delete("/api/classes/<cid>")
def api_delete_class(cid):
    if not config_store.delete_class(cid):
        raise KeyError("Class not found")
    return jsonify(ok=True)


@app.post("/api/quickjoin")
def api_quickjoin():
    b = _body()
    return jsonify(config_store.quick_join(b.get("link", ""), b.get("subject", ""), b.get("duration") or 60)), 201


@app.post("/api/settings")
def api_settings():
    config_store.update_settings(_body())
    return jsonify(ok=True)


@app.post("/api/ai/test")
def api_test_ai():
    body = _body()
    provider = str(body.get("provider") or "").strip()
    if provider not in config_store.PROVIDERS:
        raise ValueError("Choose a supported AI provider.")
    config = config_store.load_raw()
    key = str(body.get("api_key") or "").strip() or config_store.ai_key(config, provider)
    if not key:
        return jsonify(error="Enter an API key or save one before testing the connection."), 400
    model = str(body.get("model") or "").strip() or config_store.PROVIDERS[provider]["model"]
    test_config = {
        **config,
        "ai": {
            "provider": provider,
            "keys": {provider: key},
            "models": {provider: model},
        },
    }
    result = ai_notes._call(
        test_config,
        "Reply with only the word OK.",
        32,
        system="You are testing an AI provider connection. Reply only with OK.",
        api_key_override=key,
    )
    if not result:
        return jsonify(error="The provider did not return a response. Check the key and model, then try again."), 502
    return jsonify(ok=True)


# ───────────────────────── notes ─────────────────────────
@app.get("/api/notes")
def api_notes():
    out = []
    for meta in NOTES_ROOT.glob("*/*/meta.json"):
        try:
            with open(meta, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    out.sort(key=lambda m: (m.get("date", ""), m.get("time", "")), reverse=True)
    return jsonify(out[:100])


@app.get("/notes/<path:p>")
def notes_file(p):
    root = NOTES_ROOT.resolve()
    target = (root / p).resolve()
    if root not in target.parents or not target.is_file():
        abort(404)
    if target.suffix == ".md":      # show in the browser instead of downloading
        return Response(target.read_text(encoding="utf-8"), mimetype="text/plain; charset=utf-8")
    return send_from_directory(root, p)


@app.get("/notes/<path:folder>/study")
def notes_study(folder):
    directory = _note_directory(folder)
    try:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        abort(404)
    if not meta.get("done"):
        abort(409, description="These notes are still being generated.")
    document = "notes.pdf" if (directory / "notes.pdf").is_file() else "notes.html"
    if not (directory / document).is_file():
        abort(404)
    return Response(study_page.render(
        folder, meta.get("lecture_title") or meta.get("subject", "Lecture"), document
    ),
                    mimetype="text/html")


@app.post("/api/notes/<path:folder>/chat")
def notes_chat(folder):
    directory = _note_directory(folder)
    try:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        abort(404)
    if not meta.get("done"):
        return jsonify(error="These notes are still being generated."), 409

    body = _body()
    if not isinstance(body, dict):
        return jsonify(error="A JSON object is required."), 400
    question = body.get("question")
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 1000:
        return jsonify(error="Enter a question of 1 to 1000 characters."), 400
    question = question.strip()
    history = body.get("history", [])
    if not isinstance(history, list):
        return jsonify(error="Chat history must be a list of messages."), 400
    config = config_store.load_raw()
    if not ai_notes.api_key(config):
        return jsonify(error="Add an AI provider key in Dashboard → Settings to use the study chat."), 503
    transcript_path = directory / "transcript.md"
    context = (
        transcript_path.read_text(encoding="utf-8")
        if transcript_path.is_file()
        else ""
    )
    corrected_path = directory / "transcript_corrected.md"
    if corrected_path.is_file():
        notes = context.split("## Flagged moments", 1)[0].split("## Transcript", 1)[0].strip()
        corrected = corrected_path.read_text(encoding="utf-8")
        corrected_body = corrected.split("## Corrected transcript", 1)
        context = "\n\n".join(
            part for part in (
                notes,
                corrected_body[-1].strip() if len(corrected_body) == 2 else corrected,
            ) if part
        )
    answer = ai_notes.answer_question(config, context, question, history)
    if answer is None:
        return jsonify(error="The AI provider could not answer right now. Check its key and try again."), 502
    return jsonify(answer=answer)


@app.post("/notes/<path:folder>/regenerate")
def notes_regenerate_route(folder):
    import asyncio
    from utils import notes_regenerate
    directory = _note_directory(folder)
    config = config_store.load_raw()
    if not ai_notes.api_key(config):
        return jsonify(error="Add an AI provider key in Dashboard -> Settings first."), 503
    body = _body()
    prompt = str(body.get("prompt") or "").strip()[:600] if isinstance(body, dict) else ""
    try:
        ok = asyncio.run(notes_regenerate.regenerate(directory, config, prompt))
    except Exception as e:
        return jsonify(error=f"Could not regenerate the notes: {e}"), 500
    if not ok:
        return jsonify(error="The AI could not write the notes. Check the key and limits in the log, then try again."), 502
    return jsonify(ok=True)


class DashboardServer:
    def __init__(self, config=None):
        d = (config or {}).get("dashboard", {})
        self.host = d.get("host", "127.0.0.1")
        self.port = int(d.get("port", 5000))

    def run(self):
        app.run(host=self.host, port=self.port, debug=False, use_reloader=False)
