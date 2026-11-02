"""The HTTP API: the tracker snapshot qbt-rules reads, and per-tracker fetch health.

The wiki's HTTP-API-Reference endpoint table is generated from this app's OpenAPI
schema (scripts/gen-wiki.py): give every route a `summary`, and a docstring when
it needs more than a line.

The poller is a thread. The lifespan starts it and stops it, so building the app starts
nothing: tests pass their own poller, which the app then never starts or stops.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from trackie import __description__, __version__
from trackie.config import Config
from trackie.matching import MappingStore, Matcher
from trackie.poller import Poller
from trackie.schemas import Health, Ready, Snapshot
from trackie.sources import ArrClient, ProwlarrClient, QbtClient
from trackie.store import StateStore


class CompatJSONResponse(JSONResponse):
    """JSON exactly as trackie's Flask app wrote it, so no client sees the port.

    Sorted keys, compact separators, non-ASCII escaped and a trailing newline: Flask's
    `jsonify`, byte for byte (docs/design/0001-fastapi.md).
    """

    def render(self, content: Any) -> bytes:
        text = json.dumps(content, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return f"{text}\n".encode()


def build_matcher(config: Config) -> Matcher | None:
    """Matching runs when at least one source is configured."""
    if not (config.arr_apps or config.prowlarr or config.qbittorrent):
        return None
    t = config.timeout_s
    # The secrets are revealed here, where each client puts them in its requests' headers
    return Matcher(
        MappingStore(config.state_dir / "mappings.json"),
        arr=[
            ArrClient(a.name, a.url, a.api_key.reveal(), a.api_version, t) for a in config.arr_apps
        ],
        prowlarr=(
            ProwlarrClient(config.prowlarr.url, config.prowlarr.api_key.reveal(), t)
            if config.prowlarr
            else None
        ),
        qbt=(
            QbtClient(
                config.qbittorrent.url,
                config.qbittorrent.username,
                config.qbittorrent.password.reveal(),
                t,
            )
            if config.qbittorrent
            else None
        ),
        configured_hosts={k: c.announce_hosts for k, c in config.trackers.items()},
    )


def build_poller(config: Config) -> Poller:
    return Poller(config, StateStore(config.state_dir), matcher=build_matcher(config))


def create_app(config: Config, poller: Poller | None = None) -> FastAPI:
    """The app. Without `poller`, the lifespan builds one from `config`, starts and stops it."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if poller is not None:
            yield
            return
        owned = build_poller(config)
        app.state.poller = owned
        owned.start()
        try:
            yield
        finally:
            owned.stop()

    app = FastAPI(
        title="trackie",
        version=__version__,
        description=__description__,
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.poller = poller

    def current() -> Poller:
        found: Poller | None = app.state.poller
        if found is None:
            raise HTTPException(status_code=503, detail="trackie is starting")
        return found

    @app.get(
        "/snapshot",
        summary="Every tracker's last good data, keyed by qBittorrent hash",
        tags=["snapshot"],
        response_model=Snapshot,
        response_class=CompatJSONResponse,
    )
    def snapshot() -> CompatJSONResponse:
        """What qbt-rules reads, once per run. A tracker whose fetch failed keeps its last
        good data and its `fetched_at`, so the reader can judge the age itself; a tracker
        with no data yet is absent."""
        return CompatJSONResponse(current().snapshot())

    @app.get(
        "/health",
        summary="Liveness, with each tracker's fetch status",
        tags=["health"],
        response_model=Health,
        response_class=CompatJSONResponse,
    )
    def health() -> CompatJSONResponse:
        """Always 200 while the process is up, even when `status` is `degraded`."""
        return CompatJSONResponse({"version": __version__, **current().health()})

    @app.get(
        "/readyz",
        summary="Readiness: 503 unless the poller is running",
        tags=["health"],
        response_model=Ready,
        responses={503: {"description": "The poller isn't running"}},
    )
    def readyz() -> dict[str, str]:
        if not current().running:
            raise HTTPException(status_code=503, detail="the poller is not running")
        return {"status": "ready"}

    @app.get("/version", summary="The running version", tags=["meta"])
    def get_version() -> dict[str, str]:
        return {"version": __version__}

    return app
