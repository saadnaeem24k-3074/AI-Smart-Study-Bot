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


class DashboardServer:
    def __init__(self, config=None):
        d = (config or {}).get("dashboard", {})
        self.host = d.get("host", "127.0.0.1")
        self.port = int(d.get("port", 5000))

    def run(self):
        app.run(host=self.host, port=self.port, debug=False, use_reloader=False)
