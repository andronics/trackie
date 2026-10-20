from collections.abc import Callable
from dataclasses import replace
from typing import Any

from trackie.fetch import TrackerPages
from trackie.matching import Mapping
from trackie.parsers import AccountStats, HnrPage, HnrRow, PeerRow, PeersPage, ipt, td
from trackie.snapshot import assemble, tracker_section

from .helpers import T0, tracker_cfg

Page = Callable[[str], str]
ACCOUNT = AccountStats(ratio=0.5, uploaded_b=1, downloaded_b=2, bonus=3.0, seeding=1, leeching=0)


PEER = PeerRow(
    tracker_id=0,
    name="",
    name_truncated=True,
    role="seeder",
    uploaded_b=50,
    downloaded_b=100,
    session_uploaded_b=0,
    session_downloaded_b=0,
    seed_time_s=None,
    remaining_s=3600,
    progress_pct=None,
    client="qBittorrent/5.2.4",
)
HNR = HnrRow(
    tracker_id=0,
    name="",
    uploaded_b=0,
    downloaded_b=100,
    gap_b=100,
    seed_time_s=0,
    stopped_ago_s=None,
    clear_cost_points=10.0,
)


def peer(tid: int, **kw: Any) -> PeerRow:
    return replace(PEER, tracker_id=tid, name=f"Torrent {tid}...", **kw)


def hnr(tid: int, **kw: Any) -> HnrRow:
    return replace(HNR, tracker_id=tid, name=f"Torrent {tid} Full Name", **kw)


def pages(peers: list[PeerRow], hnrs: list[HnrRow]) -> TrackerPages:
    return TrackerPages(
        tracker="td",
        user_id=1000000,
        peers=PeersPage(account=ACCOUNT, rows=peers),
        hnr=HnrPage(account=ACCOUNT, rows=hnrs),
        fetched_at=T0,
    )


def records(p: TrackerPages) -> dict[int, dict[str, object]]:
    return {r["tracker_id"]: r for r in tracker_section(p, tracker_cfg("td"))["records"]}


def test_status_precedence() -> None:
    recs = records(
        pages(
            [
                peer(1, remaining_s=7200),
                peer(2, remaining_s=None, seed_time_s=999999),
                peer(3, role="leecher", remaining_s=None),
                peer(4, remaining_s=None, seed_time_s=1),  # also on H&R: hnr wins
            ],
            [hnr(4), hnr(5)],
        )
    )
    assert {tid: r["status"] for tid, r in recs.items()} == {
        1: "required",
        2: "satisfied",
        3: "required",
        4: "hnr",
        5: "hnr",
    }


def test_record_fields_merge_both_pages() -> None:
    recs = records(pages([peer(4, uploaded_b=30, downloaded_b=120)], [hnr(4, gap_b=90)]))
    r = recs[4]
    assert r["name"] == "Torrent 4 Full Name"  # H&R's full name beats the truncated one
    assert r["name_truncated"] is False
    assert (r["uploaded_b"], r["downloaded_b"], r["ratio"]) == (30, 120, 0.25)
    assert r["gap_b"] == 90
    assert r["on_peers"] and r["on_hnr"]
    assert r["seen_at"] == "2026-10-20T12:00:00Z"


def test_hnr_only_record_uses_hnr_totals() -> None:
    r = records(pages([], [hnr(9, uploaded_b=0, downloaded_b=500)]))[9]
    assert (r["uploaded_b"], r["downloaded_b"], r["ratio"]) == (0, 500, 0.0)
    assert r["remaining_s"] is None and not r["on_peers"]


def test_account_includes_site_rules_and_live_hnr_count(page: Page) -> None:
    p = TrackerPages(
        tracker="ipt",
        user_id=1000000,
        peers=ipt.parse_peers(page("ipt_peers")),
        hnr=ipt.parse_hnr(page("ipt_hnr")),
        fetched_at=T0,
    )
    account = tracker_section(p, tracker_cfg("ipt", announce_hosts=("a.example",)))["account"]
    assert account["hnr_count"] == 9
    assert (account["hnr_limit"], account["hnr_grace_s"], account["min_ratio"]) == (40, 432000, 1.0)
    assert account["announce_hosts"] == ["a.example"]
    assert "user_id" not in account


def test_real_pages_status_counts(page: Page) -> None:
    p = TrackerPages(
        tracker="td",
        user_id=1000000,
        peers=td.parse_peers(page("td_peers")),
        hnr=td.parse_hnr(page("td_hnr")),
        fetched_at=T0,
    )
    statuses = [r["status"] for r in tracker_section(p, tracker_cfg("td"))["records"]]
    assert statuses.count("required") == 17
    assert statuses.count("hnr") == 2
    assert statuses.count("satisfied") == 155


def test_assemble_shape() -> None:
    section = tracker_section(pages([peer(1)], []), tracker_cfg("td"))
    snap = assemble({"td": section}, T0)
    assert snap["fetched_at"] == {"td": "2026-10-20T12:00:00Z"}
    assert snap["accounts"]["td"]["ratio"] == 0.5
    assert snap["torrents"] == {}
    assert [r["tracker_id"] for r in snap["unmatched"]] == [1]


class FakeMappings:
    def __init__(self, table: dict[tuple[str, int], str]) -> None:
        self.table = table

    def lookup(self, tracker: str, tracker_id: int) -> Any:
        h = self.table.get((tracker, tracker_id))
        return None if h is None else Mapping(h, "exact", "sonarr", "2026-10-20T00:00:00Z")

    def hosts_for(self, tracker: str) -> list[str]:
        return ["learned.example"]


def test_assemble_partitions_by_mapping() -> None:
    section = tracker_section(pages([peer(1), peer(2), peer(3)], []), tracker_cfg("td"))
    # 3 maps to the same hash as 1: only the first keeps it
    snap = assemble({"td": section}, T0, FakeMappings({("td", 1): "a" * 40, ("td", 3): "a" * 40}))
    assert list(snap["torrents"]) == ["a" * 40]
    t = snap["torrents"]["a" * 40]
    assert (t["tracker_id"], t["hash"], t["match"], t["match_source"]) == (
        1,
        "a" * 40,
        "exact",
        "sonarr",
    )
    assert sorted(r["tracker_id"] for r in snap["unmatched"]) == [2, 3]
    assert all(r["hash"] is None for r in snap["unmatched"])


def test_assemble_merges_learned_announce_hosts() -> None:
    section = tracker_section(pages([], []), tracker_cfg("td", announce_hosts=("conf.example",)))
    snap = assemble({"td": section}, T0, FakeMappings({}))
    assert snap["accounts"]["td"]["announce_hosts"] == ["conf.example", "learned.example"]
