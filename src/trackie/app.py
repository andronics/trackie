"""HTTP API: serves the tracker snapshot and per-tracker fetch health."""

from typing import Any

from flask import Flask, jsonify

from trackie.__version__ import __version__


def empty_snapshot() -> dict[str, Any]:
    """Snapshot shape before any tracker has been fetched."""
    return {"fetched_at": {}, "accounts": {}, "torrents": {}}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok", "version": __version__, "trackers": {}})

    @app.get("/snapshot")
    def snapshot() -> Any:
        return jsonify(empty_snapshot())

    return app
