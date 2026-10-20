"""HTTP API: serves the tracker snapshot and per-tracker fetch health."""

import logging
import os
from typing import Any

from flask import Flask, jsonify

from trackie.__version__ import __version__
from trackie.config import Config, load_config
from trackie.matching import MappingStore, Matcher
from trackie.poller import Poller
from trackie.sources import ArrClient, ProwlarrClient, QbtClient
from trackie.store import StateStore


def build_matcher(config: Config) -> Matcher | None:
    """Matching runs when at least one source is configured."""
    if not (config.arr_apps or config.prowlarr or config.qbittorrent):
        return None
    t = config.timeout_s
    return Matcher(
        MappingStore(config.state_dir / "mappings.json"),
        arr=[ArrClient(a.name, a.url, a.api_key, a.api_version, t) for a in config.arr_apps],
        prowlarr=(
            ProwlarrClient(config.prowlarr.url, config.prowlarr.api_key, t)
            if config.prowlarr
            else None
        ),
        qbt=(
            QbtClient(
                config.qbittorrent.url, config.qbittorrent.username, config.qbittorrent.password, t
            )
            if config.qbittorrent
            else None
        ),
        configured_hosts={k: c.announce_hosts for k, c in config.trackers.items()},
    )


def create_app(config: Config | None = None, poller: Poller | None = None) -> Flask:
    """gunicorn entry point. Starts the poller unless one is passed in (tests)."""
    logging.basicConfig(
        level=os.environ.get("TRACKIE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if poller is None:
        config = config or load_config()
        poller = Poller(config, StateStore(config.state_dir), matcher=build_matcher(config))
        poller.start()

    app = Flask(__name__)

    @app.get("/health")
    def health() -> Any:
        return jsonify({"version": __version__, **poller.health()})

    @app.get("/snapshot")
    def snapshot() -> Any:
        return jsonify(poller.snapshot())

    return app
