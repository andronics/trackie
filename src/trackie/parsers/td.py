"""TorrentDay: Peers (/peers?u=<uid>) and Hit & Run (/seed_back.php) pages.

TD uses semantic tdm-* classes: one tdm-peers-card section per role on the
Peers page, and a tdm-seedback__table on the H&R page. The header stats are
ub-stat key/value pairs.
"""

import re

from bs4 import BeautifulSoup, Tag

from trackie.parsers.common import (
    PRIVATE_COLUMNS,
    cell,
    duration,
    header_index,
    is_truncated,
    percent,
    require_columns,
    seed_time,
    session_lifetime,
    size,
    soup,
    text,
    tracker_id,
)
from trackie.parsers.models import AccountStats, HnrPage, HnrRow, ParseError, PeerRow, PeersPage
from trackie.units import parse_number

_PEERS_ID = re.compile(r"[?;&]t=(\d+)")
_HNR_ID = re.compile(r"details\.php\?id=(\d+)")
_INT = re.compile(r"\d+")
_BP = re.compile(r"([\d.,]+)\s*BP", re.IGNORECASE)


def parse_account(doc: BeautifulSoup) -> AccountStats:
    stats = {
        text(s.select_one(".ub-stat__k")): text(s.select_one(".ub-stat__v"))
        for s in doc.select("#activityDiv .ub-stat")
    }
    for label in ("Ratio", "Up", "Dn"):
        if label not in stats:
            raise ParseError(f"account header has no {label!r}; logged out or layout changed?")

    def count(selector: str) -> int:
        m = _INT.search(text(doc.select_one(selector)))
        if not m:
            raise ParseError(f"account header has no {selector}")
        return int(m.group(0))

    return AccountStats(
        ratio=parse_number(stats["Ratio"]),
        uploaded_b=size(stats["Up"], "header Up"),
        downloaded_b=size(stats["Dn"], "header Dn"),
        bonus=parse_number(text(doc.select_one('a[href="/mybonus.php"] .ub-menu__count'))),
        seeding=count("#activityDiv .ub-peers__seed"),
        leeching=count("#activityDiv .ub-peers__leech"),
    )


def parse_peers(html: str) -> PeersPage:
    doc = soup(html)
    account = parse_account(doc)
    sections = doc.select("section.tdm-peers-card")
    if not sections:
        raise ParseError("no Peers sections found")

    rows: list[PeerRow] = []
    for section in sections:
        heading = text(section.select_one(".tdm-section-header__title")).lower()
        if heading.startswith("seed"):
            role = "seeder"
        elif heading.startswith("leech"):
            role = "leecher"
        else:
            raise ParseError(f"unknown Peers section {heading!r}")
        table = section.select_one("table.tdm-peers-table")
        head = table.select_one("thead tr") if table else None
        if table is None or head is None:
            raise ParseError(f"{heading} section has no table")
        cols = header_index(head)
        require_columns(cols, "torrent", "uploaded", "downloaded")
        if role == "seeder":
            require_columns(cols, "seed time")

        for tr in table.select("tbody tr"):
            cells = tr.find_all("td", recursive=False)
            link = cells[cols["torrent"]].find("a") if cells else None
            if not isinstance(link, Tag):
                raise ParseError("Peers row without a torrent link")
            name = text(link)
            up = text(cell(cells, cols, "uploaded"))
            down = text(cell(cells, cols, "downloaded"))
            session_up, lifetime_up = session_lifetime(up, f"{name}: uploaded")
            session_down, lifetime_down = session_lifetime(down, f"{name}: downloaded")
            seed_s, remaining_s = seed_time(
                text(cell(cells, cols, "seed time")), f"{name}: seed time"
            )

            rows.append(
                PeerRow(
                    tracker_id=tracker_id(str(link.get("href", "")), _PEERS_ID),
                    name=name,
                    name_truncated=is_truncated(name),
                    role="seeder" if role == "seeder" else "leecher",
                    uploaded_b=lifetime_up,
                    downloaded_b=lifetime_down,
                    session_uploaded_b=session_up,
                    session_downloaded_b=session_down,
                    seed_time_s=seed_s,
                    remaining_s=remaining_s,
                    progress_pct=percent(text(cell(cells, cols, "progress"))),
                    client=text(cell(cells, cols, "client")),
                    raw={
                        col: text(c)
                        for col, c in zip(cols, cells, strict=False)
                        if col not in PRIVATE_COLUMNS
                    },
                )
            )
    return PeersPage(account=account, rows=rows)


def _hnr_count_stat(doc: BeautifulSoup) -> int | None:
    for stat in doc.select(".tdm-seedback__stat"):
        if "h&r torrents" in text(stat.select_one(".tdm-seedback__stat-k")).lower():
            value = parse_number(text(stat.select_one(".tdm-seedback__stat-v")))
            return int(value) if value is not None else None
    return None


def parse_hnr(html: str) -> HnrPage:
    doc = soup(html)
    account = parse_account(doc)
    table = doc.select_one("table.tdm-seedback__table")
    if table is None:
        # The page states its own count; trust "no table" only when that says 0
        if _hnr_count_stat(doc) == 0:
            return HnrPage(account=account, rows=[])
        raise ParseError("no Hit & Run table and no zero H&R count found")
    head = table.select_one("thead tr")
    if head is None:
        raise ParseError("Hit & Run table has no header")
    cols = header_index(head)
    require_columns(cols, "torrent", "downloaded", "uploaded", "gap", "seeding time")

    rows: list[HnrRow] = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)
        link = cells[cols["torrent"]].find("a") if cells else None
        if not isinstance(link, Tag):
            raise ParseError("H&R row without a torrent link")
        # The link text is cut short by CSS only; the title attribute is the full name
        name = str(link.get("title") or text(link))
        bp = _BP.search(text(tr.select_one(".tdm-seedback__btn--bonus")))

        rows.append(
            HnrRow(
                tracker_id=tracker_id(str(link.get("href", "")), _HNR_ID),
                name=name,
                uploaded_b=size(text(cells[cols["uploaded"]]), f"{name}: uploaded"),
                downloaded_b=size(text(cells[cols["downloaded"]]), f"{name}: downloaded"),
                gap_b=size(text(cells[cols["gap"]]), f"{name}: gap"),
                seed_time_s=duration(text(cells[cols["seeding time"]]), f"{name}: seeding time"),
                stopped_ago_s=None,
                clear_cost_points=parse_number(bp.group(1)) if bp else None,
                raw={"clear": bp.group(0) if bp else ""},
            )
        )
    return HnrPage(account=account, rows=rows)
