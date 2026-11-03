"""IPTorrents: Peers (/peers?u=<uid>) and Hit & Run pages.

IPT renders bare <table class=t1> markup with unclosed rows and cells.
The header stats are a row of tooltip-labelled items ("Ratio", "Uploaded", ...).

The Peers page was redesigned around 2026-10-31: a <table class=pr-table> with
a Status pill per row instead of Seeders/Leechers heading rows, 100 rows a page
("Page 1 of 3"), and full names. Both layouts are parsed.
"""

import re

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

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
_T_PATH = re.compile(r"/t/(\d+)")
_PAGE_OF = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
_INTS = re.compile(r"\d+")
_POINTS = re.compile(r"([\d.,]+)\s*Points", re.IGNORECASE)
# The explanatory text under the H&R table; present even when the list is empty
_HNR_MARKER = "This list is just a record"


def parse_account(doc: BeautifulSoup) -> AccountStats:
    stats: dict[str, Tag] = {}
    for tip in doc.select(".tTipWrap > .tTip"):
        if isinstance(tip.parent, Tag):
            stats.setdefault(text(tip), tip.parent)

    def value(label: str) -> str:
        holder = stats.get(label)
        if holder is None:
            raise ParseError(f"account header has no {label!r}; logged out or layout changed?")
        return text(holder).removeprefix(label).strip()

    active = [int(n) for n in _INTS.findall(value("Active Torrents"))]
    if len(active) != 2:
        raise ParseError(f"unexpected Active Torrents value {value('Active Torrents')!r}")

    return AccountStats(
        ratio=parse_number(value("Ratio")),
        uploaded_b=size(value("Uploaded"), "header Uploaded"),
        downloaded_b=size(value("Downloaded"), "header Downloaded"),
        bonus=parse_number(value("Bonus Points")),
        seeding=active[0],
        leeching=active[1],
    )


def _find_table(doc: BeautifulSoup, *columns: str) -> tuple[Tag, dict[str, int]] | None:
    for table in doc.select("table.t1"):
        first = table.find("tr")
        if isinstance(first, Tag):
            cols = header_index(first)
            if all(c in cols for c in columns):
                return table, cols
    return None


def parse_peers(html: str) -> PeersPage:
    doc = soup(html)
    account = parse_account(doc)
    legacy = _find_table(doc, "torrent", "seeding time")
    if legacy is not None:
        return PeersPage(account=account, rows=_legacy_peer_rows(*legacy))

    table = doc.select_one("table.pr-table")
    if table is None:
        # The redesign shows a message instead of a table when nothing is active
        if doc.select_one("#pr .pr-empty") is not None:
            return PeersPage(account=account, rows=[])
        raise ParseError("no Peers table found")
    return PeersPage(account=account, rows=_peer_rows(table), next_page=_next_page(doc))


def _own_text(el: Tag) -> str:
    """The cell's text outside its child elements: "2.63 GB" without "Total 5.95 GB"."""
    return " ".join(s.strip() for s in el.children if isinstance(s, NavigableString)).strip()


def _transfer(el: Tag | None, what: str) -> tuple[int, int]:
    """Redesigned transfer cell -> (session bytes, lifetime bytes).

    "2.63 GB" with a "Total 5.95 GB" line under it is this session, then lifetime;
    without the line the two are the same. "-" means nothing this session, and a
    "494 B/s" line shows the current rate.
    """
    if el is None:
        return 0, 0
    own = _own_text(el)
    session = 0 if own in ("", "-") else size(own, what)
    # Other .pr-sub lines show the current rate ("494 B/s") while a transfer is active
    totals = [t for t in map(text, el.select(".pr-sub")) if t.startswith("Total")]
    if not totals:
        return session, session
    return session, size(totals[0].removeprefix("Total").strip(), what)


def _seeding(el: Tag | None, what: str) -> tuple[int | None, int | None]:
    """Redesigned seeding cell: "569 h" in .pr-done ("Requirement met" below) or "247 h to go"."""
    if el is None:
        return None, None
    done = el.select_one(".pr-done")
    value = text(done) if done is not None else _own_text(el)
    return seed_time("" if value == "-" else value, what)


def _peer_rows(table: Tag) -> list[PeerRow]:
    head = table.select_one("thead tr") or table.find("tr")
    if not isinstance(head, Tag):
        raise ParseError("Peers table has no header row")
    cols = header_index(head)
    require_columns(cols, "torrent", "status", "uploaded", "downloaded", "seeding")

    rows: list[PeerRow] = []
    for tr in table.select("tbody > tr"):
        cells = tr.find_all("td", recursive=False)
        if not cells or (len(cells) == 1 and cells[0].get("colspan")):
            continue  # a spacer or message row, not a torrent
        link = cells[cols["torrent"]].find("a", href=_T_PATH)
        if not isinstance(link, Tag):
            raise ParseError("Peers row without a torrent link")
        # The redesign shows full names; the title carries the same text
        name = str(link.get("title") or "").strip() or text(link)
        raw = {
            col: text(c) for col, c in zip(cols, cells, strict=False) if col not in PRIVATE_COLUMNS
        }
        session_up, lifetime_up = _transfer(cell(cells, cols, "uploaded"), f"{name}: uploaded")
        session_down, lifetime_down = _transfer(
            cell(cells, cols, "downloaded"), f"{name}: downloaded"
        )
        seed_s, remaining_s = _seeding(cell(cells, cols, "seeding"), f"{name}: seeding")
        status = text(cell(cells, cols, "status")).lower()

        rows.append(
            PeerRow(
                tracker_id=tracker_id(str(link.get("href", "")), _T_PATH),
                name=name,
                name_truncated=is_truncated(name),
                role="seeder" if status.startswith("seed") else "leecher",
                uploaded_b=lifetime_up,
                downloaded_b=lifetime_down,
                session_uploaded_b=session_up,
                session_downloaded_b=session_down,
                seed_time_s=seed_s,
                remaining_s=remaining_s,
                # No progress column any more; only the seeding-time bar has a percentage
                progress_pct=None,
                client=text(cell(cells, cols, "client")),
                raw=raw,
            )
        )
    return rows


def _next_page(doc: BeautifulSoup) -> int | None:
    pager = doc.select_one("nav.pr-pager")
    m = _PAGE_OF.search(text(pager)) if pager is not None else None
    if m is None:
        return None
    current, last = int(m.group(1)), int(m.group(2))
    return current + 1 if current < last else None


def _legacy_peer_rows(table: Tag, cols: dict[str, int]) -> list[PeerRow]:
    """The layout before 2026-10-31: Seeders/Leechers heading rows in a table.t1."""
    require_columns(cols, "torrent", "uploaded", "downloaded", "seeding time")

    rows: list[PeerRow] = []
    role: str | None = None
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 1 and cells[0].get("colspan"):
            heading = text(cells[0]).lower()
            role = "seeder" if heading.startswith("seed") else "leecher"
            continue
        if not cells:
            continue
        if role is None:
            raise ParseError("Peers row before any Seeders/Leechers heading")

        link = cells[cols["torrent"]].find("a")
        if not isinstance(link, Tag):
            raise ParseError("Peers row without a torrent link")
        name = text(link)
        raw = {
            col: text(c) for col, c in zip(cols, cells, strict=False) if col not in PRIVATE_COLUMNS
        }
        up = text(cell(cells, cols, "uploaded"))
        down = text(cell(cells, cols, "downloaded"))
        st = text(cell(cells, cols, "seeding time"))
        session_up, lifetime_up = session_lifetime(up, f"{name}: uploaded")
        session_down, lifetime_down = session_lifetime(down, f"{name}: downloaded")
        seed_s, remaining_s = seed_time(st, f"{name}: seeding time")

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
                progress_pct=percent(text(cell(cells, cols, "%"))),
                client=text(cell(cells, cols, "user agent")),
                raw=raw,
            )
        )
    return rows


def parse_hnr(html: str) -> HnrPage:
    doc = soup(html)
    account = parse_account(doc)
    found = _find_table(doc, "torrent", "gap")
    if found is None:
        if _HNR_MARKER in doc.get_text():
            return HnrPage(account=account, rows=[])
        raise ParseError("no Hit & Run table and no H&R page text found")
    table, cols = found
    require_columns(cols, "torrent", "uploaded", "downloaded", "gap", "seeding time")

    rows: list[HnrRow] = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue
        link = cells[cols["torrent"]].find("a")
        if not isinstance(link, Tag):
            raise ParseError("H&R row without a torrent link")
        name = text(link)
        st_cell = cells[cols["seeding time"]]
        tip = st_cell.find(class_="tTip")
        stopped = text(tip)
        if isinstance(tip, Tag):
            tip.extract()
        zap = tr.find("input", attrs={"type": "submit"})
        points = _POINTS.search(str(zap.get("value", ""))) if isinstance(zap, Tag) else None

        rows.append(
            HnrRow(
                tracker_id=tracker_id(str(link.get("href", "")), _T_PATH),
                name=name,
                uploaded_b=size(text(cells[cols["uploaded"]]), f"{name}: uploaded"),
                downloaded_b=size(text(cells[cols["downloaded"]]), f"{name}: downloaded"),
                gap_b=size(text(cells[cols["gap"]]), f"{name}: gap"),
                seed_time_s=duration(text(st_cell), f"{name}: seeding time"),
                stopped_ago_s=duration(stopped, f"{name}: stopped") if stopped else None,
                clear_cost_points=parse_number(points.group(1)) if points else None,
                raw={"stopped": stopped, "zap": points.group(0) if points else ""},
            )
        )
    return HnrPage(account=account, rows=rows)
