"""FinSight API. Serves the built React app from ../frontend/dist in production."""

from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

import explain
import investigation
import voice

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = Flask(__name__, static_folder=None)
CORS(app)

_cache: dict = {}


def _investigation() -> dict:
    if "inv" not in _cache:
        _cache["inv"] = investigation.build()
    return _cache["inv"]


def _explanations(refresh: bool = False) -> dict:
    if refresh or "exp" not in _cache:
        inv = _investigation()
        _cache["exp"] = explain.explain(inv["move"], inv["divergence"], inv["headlines"])
    return _cache["exp"]


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/investigation")
def get_investigation():
    if request.args.get("refresh"):
        _cache.clear()
    return jsonify(_investigation())


@app.get("/api/explanations")
def get_explanations():
    try:
        return jsonify(_explanations(refresh=bool(request.args.get("refresh"))))
    except Exception as e:  # surface missing keys / model errors to the UI instead of a 500 page
        return jsonify({"error": str(e)}), 502


@app.get("/api/briefing.mp3")
def get_briefing():
    inv = _investigation()
    try:
        exp = _explanations()
    except Exception:
        exp = None
    try:
        audio = voice.synthesize(voice.briefing_script(inv, exp))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return Response(audio, mimetype="audio/mpeg")


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    if path and (DIST / path).is_file():
        return send_from_directory(DIST, path)
    if (DIST / "index.html").is_file():
        return send_from_directory(DIST, "index.html")
    return "Frontend not built. Run `npm run build` in frontend/, or use `npm run dev`.", 404


if __name__ == "__main__":
    app.run(port=5000, debug=True)
