from pathlib import Path

from trackie import __version__
from trackie.app import create_app
from trackie.poller import Poller
from trackie.store import StateStore

from .helpers import app_config


def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    cfg = app_config(tmp_path)
    return create_app(poller=Poller(cfg, StateStore(tmp_path))).test_client()


def test_health_before_any_fetch(tmp_path: Path) -> None:
    resp = client(tmp_path).get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["version"] == __version__
    assert body["status"] == "degraded"
    assert set(body["trackers"]) == {"ipt", "td"}
    assert body["trackers"]["ipt"]["has_data"] is False


def test_snapshot_shape_before_any_fetch(tmp_path: Path) -> None:
    body = client(tmp_path).get("/snapshot").get_json()
    assert set(body) == {"generated_at", "fetched_at", "accounts", "torrents", "unmatched"}
    assert body["unmatched"] == []
