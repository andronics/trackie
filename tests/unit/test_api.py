"""The HTTP API: the routes the Flask app had, on the FastAPI app, and what qbt-rules relies on."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from trackie import __version__
from trackie.api import CompatJSONResponse, build_matcher, create_app
from trackie.config import load_config
from trackie.fetch import TrackerPages
from trackie.matching import MappingStore, Matcher
from trackie.parsers import ipt, td
from trackie.poller import Poller
from trackie.schemas import Health, Snapshot
from trackie.store import StateStore

from .helpers import T0, app_config

Page = Callable[[str], str]


def client(tmp_path: Path, poller: Poller | None = None) -> TestClient:
    cfg = app_config(tmp_path)
    return TestClient(create_app(cfg, poller=poller or Poller(cfg, StateStore(tmp_path))))


class Pages:
    """A site client that returns saved pages."""

    def __init__(self, pages: TrackerPages) -> None:
        self.pages = pages

    def fetch(self) -> TrackerPages:
        return self.pages


@pytest.fixture
def polled(tmp_path: Path, page: Page) -> Poller:
    """A poller that has fetched both trackers once, with some records matched."""
    pages = {
        "ipt": TrackerPages(
            "ipt", 1000000, ipt.parse_peers(page("ipt_peers")), ipt.parse_hnr(page("ipt_hnr")), T0
        ),
        "td": TrackerPages(
            "td", 1000000, td.parse_peers(page("td_peers")), td.parse_hnr(page("td_hnr")), T0
        ),
    }
    mappings: dict[str, Any] = {"version": 1, "hosts": {"tracker.example.org": "ipt"}}
    mappings["mappings"] = {
        key: {
            str(r.tracker_id): {
                "hash": f"{key}{i:038x}",
                "match": "exact" if i % 2 else "fuzzy",
                "source": "sonarr",
                "matched_at": "2026-10-20T11:00:00Z",
            }
            for i, r in enumerate(p.peers.rows[:3])
        }
        for key, p in pages.items()
    }
    (tmp_path / "mappings.json").write_text(json.dumps(mappings), encoding="utf-8")
    poller = Poller(
        app_config(tmp_path),
        StateStore(tmp_path),
        client_factory=lambda key: Pages(pages[key]),
        now=lambda: T0,
        matcher=Matcher(MappingStore(tmp_path / "mappings.json")),
    )
    poller.poll("ipt")
    poller.poll("td")
    return poller


# --- the Flask app's routes, unchanged ---------------------------------------------------


def test_health_before_any_fetch(tmp_path: Path) -> None:
    resp = client(tmp_path).get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == __version__
    assert body["status"] == "degraded"
    assert set(body["trackers"]) == {"ipt", "td"}
    assert body["trackers"]["ipt"]["has_data"] is False


def test_snapshot_shape_before_any_fetch(tmp_path: Path) -> None:
    body = client(tmp_path).get("/snapshot").json()
    assert set(body) == {"generated_at", "fetched_at", "accounts", "torrents", "unmatched"}
    assert body["unmatched"] == []


def test_paths_and_methods(tmp_path: Path) -> None:
    # The only routes clients use are GETs, at the paths they always had
    schema = client(tmp_path).get("/openapi.json").json()
    assert {p: sorted(ops) for p, ops in schema["paths"].items()} == {
        "/snapshot": ["get"],
        "/health": ["get"],
        "/readyz": ["get"],
        "/version": ["get"],
    }


# --- the JSON, byte for byte as Flask's jsonify wrote it ----------------------------------


def test_json_is_written_as_flask_wrote_it() -> None:
    doc = {
        "torrents": {
            "abc": {"name": "Amélie \u2013 日本", "ratio": 1.0, "gap_b": None, "on_hnr": False}
        },
        "accounts": {},
        "fetched_at": {"ipt": "2026-10-20T12:00:00Z"},
    }
    # flask.jsonify(doc).get_data() from trackie 0.1.0's Flask 3 app
    flask = (
        b'{"accounts":{},"fetched_at":{"ipt":"2026-10-20T12:00:00Z"},"torrents":{"abc":{"gap_b":'
        b'null,"name":"Am\\u00e9lie \\u2013 \\u65e5\\u672c","on_hnr":false,"ratio":1.0}}}\n'
    )
    assert CompatJSONResponse(doc).body == flask


def test_snapshot_bytes_are_the_poller_document(tmp_path: Path, polled: Poller) -> None:
    resp = client(tmp_path, polled).get("/snapshot")
    assert resp.headers["content-type"] == "application/json"
    expected = json.dumps(
        polled.snapshot(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    assert resp.content == f"{expected}\n".encode()


# --- the contract qbt-rules relies on ----------------------------------------------------

# qbt_rules/trackie.py: TORRENT_FIELDS and ACCOUNT_FIELDS (the keys it maps tracker.* to),
# plus the keys its TrackieSnapshot reads directly, with the JSON types it handles.
JSONTypes = dict[str, tuple[type, ...]]
QBT_RULES_TORRENT: JSONTypes = {
    "status": (str,),
    "remaining_s": (int, type(None)),
    "seed_time_s": (int, type(None)),
    "uploaded_b": (int,),
    "downloaded_b": (int,),
    "ratio": (float, int, type(None)),
    "gap_b": (int, type(None)),
    "hnr_seed_time_s": (int, type(None)),
    "name": (str,),
    "tracker_id": (int,),
    "tracker": (str,),
    "match": (str,),
    "match_source": (str,),
    "on_peers": (bool,),
    "on_hnr": (bool,),
    "seen_at": (str,),
}
QBT_RULES_ACCOUNT: JSONTypes = {
    "ratio": (float, int, type(None)),
    "min_ratio": (float, int),
    "uploaded_b": (int,),
    "downloaded_b": (int,),
    "bonus": (float, int, type(None)),
    "seeding": (int,),
    "leeching": (int,),
    "hnr_count": (int,),
    "hnr_limit": (int,),
    "hnr_grace_s": (int,),
    "announce_hosts": (list,),
    "seen_at": (str,),
}


def test_snapshot_contract(tmp_path: Path, polled: Poller) -> None:
    resp = client(tmp_path, polled).get("/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    # qbt-rules refuses a document without "torrents" and reads these at the top level
    assert set(body) == {"generated_at", "fetched_at", "accounts", "torrents", "unmatched"}
    assert body["fetched_at"] == {"ipt": "2026-10-20T12:00:00Z", "td": "2026-10-20T12:00:00Z"}
    assert set(body["accounts"]) == {"ipt", "td"}
    assert len(body["torrents"]) == 6
    assert body["unmatched"]
    for h, record in body["torrents"].items():
        assert record["hash"] == h
        assert record["status"] in {"required", "satisfied", "hnr"}
        assert record["match"] in {"exact", "fuzzy"}
        for key, types in QBT_RULES_TORRENT.items():
            assert type(record[key]) in types, (key, record[key])
    for account in body["accounts"].values():
        for key, types in QBT_RULES_ACCOUNT.items():
            assert type(account[key]) in types, (key, account[key])
    assert "tracker.example.org" in body["accounts"]["ipt"]["announce_hosts"]
    # Exactly what the models declare: a new field is a deliberate change
    Snapshot.model_validate(body, strict=True)


def test_health_contract(tmp_path: Path, polled: Poller) -> None:
    body = client(tmp_path, polled).get("/health").json()
    Health.model_validate(body, strict=True)
    assert body["status"] == "ok"
    assert body["matching"]["mappings"] == {"ipt": 3, "td": 3}


# --- readiness and the poller's lifespan --------------------------------------------------


def test_ready_only_while_the_poller_runs(tmp_path: Path) -> None:
    c = client(tmp_path)
    resp = c.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "the poller is not running"}


def test_lifespan_starts_and_stops_the_poller(tmp_path: Path) -> None:
    env = {
        "TRACKIE_IPT_ENABLED": "false",
        "TRACKIE_TD_ENABLED": "false",
        "TRACKIE_STATE_DIR": str(tmp_path),
    }
    app = create_app(load_config(tmp_path / "missing.yaml", environ=env))
    assert app.state.poller is None  # building the app starts nothing
    with TestClient(app) as c:
        poller = cast(Poller, app.state.poller)
        assert poller.running
        assert c.get("/readyz").json() == {"status": "ready"}
        assert c.get("/health").json()["status"] == "ok"
    assert not poller.running


def test_starting_is_503(tmp_path: Path) -> None:
    app = create_app(app_config(tmp_path))  # no poller and no lifespan run
    resp = TestClient(app).get("/snapshot")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "trackie is starting"}


def test_version(tmp_path: Path) -> None:
    assert client(tmp_path).get("/version").json() == {"version": __version__}


# --- the matcher the lifespan builds ------------------------------------------------------


def test_no_sources_no_matcher(tmp_path: Path) -> None:
    assert build_matcher(app_config(tmp_path)) is None


def test_matcher_gets_the_revealed_secrets(tmp_path: Path) -> None:
    env = {
        "TRACKIE_STATE_DIR": str(tmp_path),
        "TRACKIE_SONARR_URL": "http://sonarr:8989",
        "TRACKIE_SONARR_API_KEY": "k" * 32,
        "TRACKIE_PROWLARR_URL": "http://prowlarr:9696",
        "TRACKIE_PROWLARR_API_KEY": "p" * 32,
        "TRACKIE_QBITTORRENT_URL": "http://qbt:8080",
        "TRACKIE_QBITTORRENT_USERNAME": "admin",
        "TRACKIE_QBITTORRENT_PASSWORD": "pw",
    }
    matcher = build_matcher(load_config(tmp_path / "missing.yaml", environ=env))
    assert matcher is not None
    assert matcher.arr[0].session.headers["X-Api-Key"] == "k" * 32  # type: ignore[attr-defined]
    assert matcher.prowlarr is not None
    assert matcher.prowlarr.session.headers["X-Api-Key"] == "p" * 32  # type: ignore[attr-defined]
    assert matcher.qbt is not None
    assert matcher.qbt.password == "pw"  # type: ignore[attr-defined]  # noqa: S105
