from trackie import __version__
from trackie.app import create_app


def test_health_reports_version() -> None:
    client = create_app().test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["version"] == __version__


def test_snapshot_has_expected_top_level_keys() -> None:
    client = create_app().test_client()
    resp = client.get("/snapshot")
    assert resp.status_code == 200
    assert set(resp.get_json()) == {"fetched_at", "accounts", "torrents"}
