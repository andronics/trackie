"""Parsers against scrubbed pages saved from both sites on 2026-10-20.

Expected counts were checked by hand against the live pages when saved.
"""

import re
from collections.abc import Callable

import pytest

from trackie.parsers import ParseError, ipt, td

GB = 1024**3
MB = 1024**2
DAY = 86400
WEEK = 7 * DAY

Page = Callable[[str], str]


# --- IPT Peers ---------------------------------------------------------------


def test_ipt_peers_rows(page: Page) -> None:
    result = ipt.parse_peers(page("ipt_peers"))
    rows = result.rows
    assert len(rows) == 129
    assert all(r.role == "seeder" for r in rows)
    assert sum(r.remaining_s is not None for r in rows) == 70
    assert sum(r.seed_time_s is not None for r in rows) == 59
    assert sum(r.name_truncated for r in rows) == 78
    # Exactly one of seed_time_s / remaining_s on every row
    assert all((r.seed_time_s is None) != (r.remaining_s is None) for r in rows)
    assert len({r.tracker_id for r in rows}) == 129


def test_ipt_peers_row_values(page: Page) -> None:
    rows = {r.tracker_id: r for r in ipt.parse_peers(page("ipt_peers")).rows}

    open_row = rows[7766504]
    assert open_row.name == "A Remarkable Place To Die S02E05 1080p TVNZ WEB..."
    assert open_row.name_truncated
    assert open_row.uploaded_b == round(197 * MB)
    assert open_row.downloaded_b == round(2.04 * GB)
    assert open_row.session_uploaded_b == 0
    assert open_row.remaining_s == round(4.9 * DAY)
    assert open_row.seed_time_s is None
    assert open_row.client == "qBittorrent/5.2.4"

    met = rows[7460264]
    assert met.name == "A Good Girls Guide to Murder S02E04 480p x264-mSD"
    assert not met.name_truncated
    assert met.uploaded_b == 0  # empty cell: nothing uploaded yet
    assert met.downloaded_b == round(341 * MB)
    assert met.seed_time_s == round(2.1 * WEEK)
    assert met.remaining_s is None


def test_ipt_peers_raw_has_no_private_columns(page: Page) -> None:
    for row in ipt.parse_peers(page("ipt_peers")).rows:
        assert not {"user", "ip address"} & row.raw.keys()
        assert row.raw["seeding time"]


def test_ipt_account(page: Page) -> None:
    account = ipt.parse_peers(page("ipt_peers")).account
    assert account.ratio == pytest.approx(0.410)
    assert account.uploaded_b == 172 * GB
    assert account.downloaded_b == 421 * GB
    assert account.bonus == pytest.approx(7305.3)
    assert (account.seeding, account.leeching) == (124, 0)


# --- IPT Hit & Run -----------------------------------------------------------


def test_ipt_hnr_rows(page: Page) -> None:
    rows = ipt.parse_hnr(page("ipt_hnr")).rows
    assert len(rows) == 9
    first = rows[0]
    assert first.tracker_id == 6687960
    assert first.name == "Animal Kingdom 2016 S03 720p AMZN WEB-DL DD 5 1 H 264-playWEB"
    assert first.uploaded_b == 0
    assert first.downloaded_b == round(3.17 * GB)
    assert first.gap_b == round(3.17 * GB)
    assert first.seed_time_s == 0
    assert first.stopped_ago_s == round(508.1 * 3600)
    assert first.clear_cost_points == pytest.approx(317.02)
    assert rows[1].uploaded_b == round(25.94 * MB)


def test_ipt_hnr_empty_list_is_valid(page: Page) -> None:
    html = re.sub(
        r"<table class=t1><tr><th class=al>Torrent.*?</table>", "", page("ipt_hnr"), flags=re.S
    )
    assert ipt.parse_hnr(html).rows == []


# --- TD Peers ----------------------------------------------------------------


def test_td_peers_rows(page: Page) -> None:
    rows = td.parse_peers(page("td_peers")).rows
    assert len(rows) == 172
    assert all(r.role == "seeder" for r in rows)
    assert sum(r.remaining_s is not None for r in rows) == 17
    assert sum(r.name_truncated for r in rows) == 110
    assert all((r.seed_time_s is None) != (r.remaining_s is None) for r in rows)
    # Never more than TD's 72 h requirement ("3.0 days to go" on a fresh torrent)
    assert all(r.remaining_s <= 3 * DAY for r in rows if r.remaining_s is not None)


def test_td_peers_row_values(page: Page) -> None:
    rows = {r.tracker_id: r for r in td.parse_peers(page("td_peers")).rows}

    met = rows[10224043]
    assert met.name == "12 Rounds 2009 1080p BluRay DD 5 1 x264-playHD"
    assert met.uploaded_b == round(15.4 * GB)
    assert met.downloaded_b == round(17.1 * GB)
    assert met.seed_time_s == round(1.5 * WEEK)

    open_row = rows[10329334]
    assert open_row.name_truncated
    assert open_row.remaining_s == 23 * 3600


def test_td_account(page: Page) -> None:
    account = td.parse_peers(page("td_peers")).account
    assert account.ratio == pytest.approx(1.851)
    assert account.uploaded_b == 890 * GB
    assert account.downloaded_b == 481 * GB
    assert account.bonus == pytest.approx(2636.7)
    assert (account.seeding, account.leeching) == (172, 0)


# --- TD Hit & Run ------------------------------------------------------------


def test_td_hnr_rows(page: Page) -> None:
    rows = td.parse_hnr(page("td_hnr")).rows
    assert [r.tracker_id for r in rows] == [10241322, 9636354]
    first = rows[0]
    assert first.name == "Tuner 2026 1080p BluRay REMUX AVC tmos-TRiToN"
    assert first.downloaded_b == round(2.33 * GB)
    assert first.uploaded_b == 0
    assert first.gap_b == round(2.33 * GB)
    assert first.seed_time_s == 0
    assert first.stopped_ago_s is None
    assert first.clear_cost_points == 233


def test_td_hnr_empty_list_needs_zero_count(page: Page) -> None:
    no_table = re.sub(
        r'<table class="tdm-seedback__table">.*?</table>', "", page("td_hnr"), flags=re.S
    )
    # The page still says 2 H&R torrents, so a missing table is a layout problem
    with pytest.raises(ParseError):
        td.parse_hnr(no_table)
    zero = re.sub(
        r'(H&amp;R Torrents</span>\s*<span class="tdm-seedback__stat-v">)2<', r"\g<1>0<", no_table
    )
    assert td.parse_hnr(zero).rows == []


# --- Failure modes -----------------------------------------------------------

LOGIN_PAGE = (
    "<html><head><title>Login</title></head><body><form><input name=username></form></body></html>"
)


@pytest.mark.parametrize("parse", [ipt.parse_peers, ipt.parse_hnr, td.parse_peers, td.parse_hnr])
def test_login_page_is_an_error_not_empty(parse: Callable[[str], object]) -> None:
    with pytest.raises(ParseError):
        parse(LOGIN_PAGE)


def test_ipt_peers_missing_table_is_an_error(page: Page) -> None:
    html = re.sub(
        r"<table class=t1><tr><th><a[^>]*>Torrent.*?</table>", "", page("ipt_peers"), flags=re.S
    )
    with pytest.raises(ParseError, match="no Peers table"):
        ipt.parse_peers(html)


def test_td_peers_missing_column_is_an_error(page: Page) -> None:
    html = page("td_peers").replace(">Seed Time</a>", ">Seeded</a>")
    with pytest.raises(ParseError, match="missing columns"):
        td.parse_peers(html)


def test_ipt_peers_unknown_duration_is_an_error(page: Page) -> None:
    html = page("ipt_peers").replace("4.9 days to go", "4.9 fortnights to go", 1)
    with pytest.raises(ParseError, match="fortnights"):
        ipt.parse_peers(html)


def test_ipt_hnr_page_without_marker_is_an_error(page: Page) -> None:
    html = re.sub(
        r"<table class=t1><tr><th class=al>Torrent.*?</table>", "", page("ipt_hnr"), flags=re.S
    )
    html = html.replace("This list is just a record", "Something else")
    with pytest.raises(ParseError):
        ipt.parse_hnr(html)
