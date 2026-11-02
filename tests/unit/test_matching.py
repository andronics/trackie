from pathlib import Path
from typing import Any

import pytest

from trackie.matching import MappingStore, Matcher, normalise
from trackie.sources import Grab, QbtTorrent, SourceError

H1, H2, H3, H4 = "1" * 40, "2" * 40, "3" * 40, "4" * 40
IPT_HOST, TD_HOST = "routing.bgp.technology", "sync.td-peers.com"


class FakeHistory:
    def __init__(self, name: str, grabs: list[Grab] | Exception) -> None:
        self.name = name
        self._grabs = grabs
        self.since: list[str | None] = []

    def grabs(self, since: str | None = None) -> list[Grab]:
        self.since.append(since)
        if isinstance(self._grabs, Exception):
            raise self._grabs
        return [g for g in self._grabs if since is None or g.date >= since]


class FakeQbt:
    def __init__(self, torrents: list[QbtTorrent]) -> None:
        self._torrents = torrents

    def torrents(self) -> list[QbtTorrent]:
        return self._torrents


def grab(url: str, hash_: str | None, title: str = "", date: str = "2026-10-20T00:00:00Z") -> Grab:
    return Grab(date=date, url=url, title=title, hash=hash_, app="sonarr")


def rec(tid: int, name: str, truncated: bool = False, downloaded: int = 0) -> dict[str, Any]:
    return {
        "tracker_id": tid,
        "name": name,
        "name_truncated": truncated,
        "downloaded_b": downloaded,
    }


def torrent(hash_: str, name: str, size: int = 1000, host: str | None = IPT_HOST) -> QbtTorrent:
    return QbtTorrent(hash=hash_, name=name, size=size, host=host)


def matcher(tmp_path: Path, **kw: Any) -> Matcher:
    return Matcher(MappingStore(tmp_path / "mappings.json"), **kw)


def test_normalise() -> None:
    assert normalise("Show.Name_S01E01  1080p") == "show name s01e01 1080p"


def test_arr_history_gives_exact_mappings_for_both_trackers(tmp_path: Path) -> None:
    sonarr = FakeHistory(
        "sonarr",
        [
            grab("https://iptorrents.com/t/100", H1),
            grab("https://www.torrentday.com/details.php?id=200", H2),
            grab("https://example.org/t/300", H3),  # another indexer
        ],
    )
    m = matcher(tmp_path, arr=[sonarr])
    report = m.refresh({})
    assert m.lookup("ipt", 100).hash == H1  # type: ignore[union-attr]
    assert m.lookup("td", 200).match == "exact"  # type: ignore[union-attr]
    assert m.lookup("ipt", 300) is None
    assert report.new == {"sonarr": 2}


def test_checkpoint_makes_history_incremental(tmp_path: Path) -> None:
    sonarr = FakeHistory(
        "sonarr", [grab("https://iptorrents.com/t/1", H1, date="2026-10-20T05:00:00Z")]
    )
    matcher(tmp_path, arr=[sonarr]).refresh({})
    matcher(tmp_path, arr=[sonarr]).refresh({})
    assert sonarr.since == [None, "2026-10-20T05:00:00Z"]


def test_mappings_survive_restart(tmp_path: Path) -> None:
    matcher(
        tmp_path, arr=[FakeHistory("sonarr", [grab("https://iptorrents.com/t/1", H1)])]
    ).refresh({})
    # History has since lost the grab (series deleted): the mapping stays
    m = matcher(tmp_path, arr=[FakeHistory("sonarr", [])])
    m.refresh({})
    assert m.lookup("ipt", 1).hash == H1  # type: ignore[union-attr]


def test_prowlarr_title_matches_qbittorrent_name(tmp_path: Path) -> None:
    prowlarr = FakeHistory(
        "prowlarr",
        [
            grab(
                "https://iptorrents.com/download.php/7/x.torrent", None, "Show.S05E01.1080p.WEB-GRP"
            )
        ],
    )
    qbt = FakeQbt([torrent(H1, "Show S05E01 1080p WEB-GRP"), torrent(H2, "Other")])
    m = matcher(tmp_path, prowlarr=prowlarr, qbt=qbt, configured_hosts={"ipt": [IPT_HOST]})
    m.refresh({"ipt": [rec(7, "Show S05E01 1080p W...", truncated=True)]})
    mapping = m.lookup("ipt", 7)
    assert mapping is not None
    assert (mapping.hash, mapping.match, mapping.source) == (H1, "exact", "prowlarr")


def test_full_hnr_name_is_a_fuzzy_match(tmp_path: Path) -> None:
    qbt = FakeQbt([torrent(H1, "Hot.Milk.2025.1080p.BluRay"), torrent(H2, "Hot Milk 2025 720p")])
    m = matcher(tmp_path, qbt=qbt, configured_hosts={"ipt": [IPT_HOST]})
    m.refresh({"ipt": [rec(9, "Hot Milk 2025 1080p BluRay")]})
    mapping = m.lookup("ipt", 9)
    assert mapping is not None and (mapping.hash, mapping.match, mapping.source) == (
        H1,
        "fuzzy",
        "name",
    )


@pytest.mark.parametrize(
    ("downloaded", "expected"),
    [(1050, H1), (1000, H1), (2000, None), (900, None)],
)
def test_truncated_name_needs_size_to_agree(
    tmp_path: Path, downloaded: int, expected: str | None
) -> None:
    qbt = FakeQbt([torrent(H1, "A Remarkable Place To Die S02E05 1080p TVNZ WEB-DL", size=1000)])
    m = matcher(tmp_path, qbt=qbt, configured_hosts={"ipt": [IPT_HOST]})
    m.refresh(
        {"ipt": [rec(5, "A Remarkable Place To Die S02E05 1080p TVNZ WEB...", True, downloaded)]}
    )
    mapping = m.lookup("ipt", 5)
    assert (mapping.hash if mapping else None) == expected


def test_ambiguous_or_short_prefix_is_left_unmatched(tmp_path: Path) -> None:
    qbt = FakeQbt(
        [
            torrent(H1, "Long Running Show S01E01 1080p WEB-A", size=1000),
            torrent(H2, "Long Running Show S01E01 1080p WEB-B", size=1000),
            torrent(H3, "Short", size=1000),
        ]
    )
    m = matcher(tmp_path, qbt=qbt, configured_hosts={"ipt": [IPT_HOST]})
    m.refresh(
        {
            "ipt": [
                rec(1, "Long Running Show S01E01 1080p WEB...", True, 1000),
                rec(2, "Short...", True, 1000),
            ]
        }
    )
    assert m.lookup("ipt", 1) is None
    assert m.lookup("ipt", 2) is None


def test_name_matching_only_considers_the_trackers_own_torrents(tmp_path: Path) -> None:
    qbt = FakeQbt([torrent(H1, "Same Name", host=TD_HOST)])
    m = matcher(tmp_path, qbt=qbt, configured_hosts={"ipt": [IPT_HOST], "td": [TD_HOST]})
    m.refresh({"ipt": [rec(1, "Same Name")]})
    assert m.lookup("ipt", 1) is None


def test_hosts_are_learned_by_clear_majority(tmp_path: Path) -> None:
    grabs = [grab(f"https://iptorrents.com/t/{i}", f"{i:040d}") for i in range(10)]
    grabs.append(grab("https://www.torrentday.com/details.php?id=1", f"{0:040d}"))  # cross-posted
    grabs += [
        grab(f"https://www.torrentday.com/details.php?id={i}", f"{i:040x}") for i in range(20, 22)
    ]
    qbt = FakeQbt(
        [torrent(f"{i:040d}", f"ipt {i}", host="ipt.example") for i in range(10)]
        + [torrent(f"{i:040x}", f"td {i}", host="td.example") for i in range(20, 22)]
    )
    m = matcher(tmp_path, arr=[FakeHistory("sonarr", grabs)], qbt=qbt)
    m.refresh({})
    assert m.state.hosts == {"ipt.example": "ipt"}  # td.example has only 2 votes
    assert m.hosts_for("ipt") == ["ipt.example"]


def test_exact_mapping_is_never_replaced(tmp_path: Path) -> None:
    m = matcher(tmp_path, arr=[FakeHistory("sonarr", [grab("https://iptorrents.com/t/1", H1)])])
    m.refresh({})
    m.arr = [FakeHistory("radarr", [grab("https://iptorrents.com/t/1", H2)])]
    m.refresh({})
    assert m.lookup("ipt", 1).hash == H1  # type: ignore[union-attr]


def test_fuzzy_mapping_is_upgraded_by_exact(tmp_path: Path) -> None:
    qbt = FakeQbt([torrent(H1, "Some Movie 2025 1080p")])
    m = matcher(tmp_path, qbt=qbt, configured_hosts={"ipt": [IPT_HOST]})
    m.refresh({"ipt": [rec(4, "Some Movie 2025 1080p")]})
    assert m.lookup("ipt", 4).match == "fuzzy"  # type: ignore[union-attr]
    m.arr = [FakeHistory("radarr", [grab("https://iptorrents.com/t/4", H4)])]
    m.refresh({})
    mapping = m.lookup("ipt", 4)
    assert mapping is not None and (mapping.hash, mapping.match) == (H4, "exact")


def test_one_failing_source_does_not_stop_the_others(tmp_path: Path) -> None:
    m = matcher(
        tmp_path,
        arr=[
            FakeHistory("sonarr", SourceError("sonarr: HTTP 500")),
            FakeHistory("radarr", [grab("https://iptorrents.com/t/1", H1)]),
        ],
    )
    report = m.refresh({})
    assert report.errors == {"sonarr": "sonarr: HTTP 500"}
    assert m.lookup("ipt", 1) is not None


def test_corrupt_store_is_kept_aside(tmp_path: Path) -> None:
    path = tmp_path / "mappings.json"
    path.write_text("{oops")
    assert MappingStore(path).load().mappings == {}
    assert (tmp_path / "mappings.corrupt").exists()
