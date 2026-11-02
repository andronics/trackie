from pathlib import Path

from trackie.store import StateStore


def test_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    assert store.load("ipt") is None
    store.save("ipt", {"fetched_at": "x", "records": [1, 2]})
    assert store.load("ipt") == {"fetched_at": "x", "records": [1, 2]}
    assert [p.name for p in (tmp_path / "state").iterdir()] == ["ipt.json"]


def test_corrupt_file_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "td.json").write_text("{not json")
    assert StateStore(tmp_path).load("td") is None
