from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from trackie.fetch import AuthError, FetchError, TrackerPages
from trackie.parsers import ParseError, td
from trackie.poller import Poller
from trackie.store import StateStore

from .helpers import T0, app_config

Page = Callable[[str], str]


class FakeClient:
    def __init__(self, results: list[TrackerPages | Exception]) -> None:
        self.results = results
        self.calls = 0

    def fetch(self) -> TrackerPages:
        result = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def good(page: Page) -> TrackerPages:
    return TrackerPages(
        tracker="td",
        user_id=1000000,
        peers=td.parse_peers(page("td_peers")),
        hnr=td.parse_hnr(page("td_hnr")),
        fetched_at=T0,
    )


def make(
    tmp_path: Path, results: list[TrackerPages | Exception], clock: Clock | None = None
) -> tuple[Poller, FakeClient]:
    cfg = app_config(tmp_path)
    cfg.trackers.pop("ipt")
    fake = FakeClient(results)
    poller = Poller(
        cfg, StateStore(tmp_path), client_factory=lambda key: fake, now=clock or Clock()
    )  # type: ignore[arg-type,return-value]
    return poller, fake


def test_success_fills_snapshot_health_and_store(tmp_path: Path, good: TrackerPages) -> None:
    poller, _ = make(tmp_path, [good])
    poller.run_due()
    snap = poller.snapshot()
    assert len(snap["unmatched"]) == 174  # 172 Peers + 2 H&R-only
    assert snap["accounts"]["td"]["hnr_count"] == 2
    health = poller.health()
    assert health["status"] == "ok"
    assert health["trackers"]["td"]["cookie_ok"] is True
    assert (tmp_path / "td.json").exists()


@pytest.mark.parametrize(
    ("error", "kind", "cookie_ok"),
    [
        (AuthError("login page"), "auth", False),
        (FetchError("HTTP 502"), "fetch", True),
        (ParseError("no table"), "parse", True),
        (RuntimeError("boom"), "error", True),
    ],
)
def test_failure_keeps_last_good_data(
    tmp_path: Path, good: TrackerPages, error: Exception, kind: str, cookie_ok: bool
) -> None:
    clock = Clock()
    poller, _ = make(tmp_path, [good, error], clock)
    poller.run_due()
    before = poller.snapshot()["fetched_at"]
    clock.now += timedelta(hours=1)
    poller.run_due()
    assert poller.snapshot()["fetched_at"] == before
    t = poller.health()["trackers"]["td"]
    assert poller.health()["status"] == "degraded"
    assert (t["error_kind"], t["cookie_ok"], t["failures"], t["has_data"]) == (
        kind,
        cookie_ok,
        1,
        True,
    )


def test_zero_rows_after_many_is_rejected(tmp_path: Path, good: TrackerPages) -> None:
    # Header says nothing seeding either, so only the drop itself is suspicious
    quiet = replace(good.peers.account, seeding=0)
    empty = replace(good, peers=replace(good.peers, account=quiet, rows=[]))
    clock = Clock()
    poller, _ = make(tmp_path, [good, empty], clock)
    poller.run_due()
    clock.now += timedelta(hours=1)
    poller.run_due()
    assert poller.health()["trackers"]["td"]["error_kind"] == "suspect"
    assert len(poller.snapshot()["unmatched"]) == 174


def test_zero_rows_while_header_says_seeding_is_rejected(
    tmp_path: Path, good: TrackerPages
) -> None:
    empty = replace(good, peers=replace(good.peers, rows=[]))
    poller, _ = make(tmp_path, [empty])
    poller.run_due()
    assert poller.health()["trackers"]["td"]["error_kind"] == "suspect"
    assert poller.snapshot()["unmatched"] == []


def test_genuinely_empty_first_fetch_is_accepted(tmp_path: Path, good: TrackerPages) -> None:
    quiet = replace(good.peers.account, seeding=0)
    empty = replace(good, peers=replace(good.peers, account=quiet, rows=[]))
    poller, _ = make(tmp_path, [empty])
    poller.run_due()
    assert poller.health()["trackers"]["td"]["ok"] is True


def test_backoff_doubles_and_caps(tmp_path: Path) -> None:
    clock = Clock()
    poller, fake = make(tmp_path, [FetchError("down")], clock)
    delays = []
    for _ in range(5):
        poller.run_due()
        nxt = poller.states["td"].next_poll
        assert nxt is not None
        delays.append((nxt - clock.now).total_seconds())
        clock.now = nxt
    assert delays == [5400, 10800, 21600, 21600, 21600]
    assert fake.calls == 5


def test_not_due_means_no_fetch(tmp_path: Path, good: TrackerPages) -> None:
    clock = Clock()
    poller, fake = make(tmp_path, [good], clock)
    poller.run_due()
    clock.now += timedelta(minutes=44)
    poller.run_due()
    assert fake.calls == 1
    clock.now += timedelta(minutes=2)
    poller.run_due()
    assert fake.calls == 2


def test_persisted_section_survives_restart(tmp_path: Path, good: TrackerPages) -> None:
    first, _ = make(tmp_path, [good])
    first.run_due()
    second, _ = make(tmp_path, [FetchError("down")])
    assert len(second.snapshot()["unmatched"]) == 174
    assert second.health()["trackers"]["td"]["cookie_ok"] is None
