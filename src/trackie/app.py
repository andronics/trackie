"""HTTP API: serves the tracker snapshot and per-tracker fetch health."""

import logging
import os
from typing import Any

from flask import Flask, jsonify

from trackie.__version__ import __version__
from trackie.config import Config, load_config
from trackie.poller import Poller
from trackie.store import StateStore


def create_app(config: Config | None = None, poller: Poller | None = None) -> Flask:
    """gunicorn entry point. Starts the poller unless one is passed in (tests)."""
    logging.basicConfig(
        level=os.environ.get("TRACKIE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if poller is None:
        config = config or load_config()
        poller = Poller(config, StateStore(config.state_dir))
        poller.start()

    app = Flask(__name__)

    @app.get("/health")
    def health() -> Any:
        return jsonify({"version": __version__, **poller.health()})

    @app.get("/snapshot")
    def snapshot() -> Any:
        return jsonify(poller.snapshot())

    return app
