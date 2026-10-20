"""Helpers shared by the site parsers."""

import re

from bs4 import BeautifulSoup, Tag

from trackie.parsers.models import ParseError
from trackie.units import UnitError, parse_duration, parse_size

# Never copied into PeerRow.raw: they hold the account name and home IP
PRIVATE_COLUMNS = frozenset({"user", "ip", "ip address"})

# "0 B (35.7 MB)": this session's transfer, then lifetime in brackets
_SESSION_LIFETIME = re.compile(r"^\s*(.+?)\s*\((.+)\)\s*$")


def soup(html: str) -> BeautifulSoup:
    # lxml closes IPT's bare <tr><td> markup the way a browser does;
    # html.parser would nest every cell inside the one before it
    return BeautifulSoup(html, "lxml")


def text(el: Tag | None) -> str:
    return el.get_text(" ", strip=True) if el else ""


def header_index(row: Tag) -> dict[str, int]:
    """Column name -> position, so a reordered or added column doesn't shift fields.

    Repeated names get a numeric suffix ("rate", "rate 2"), keeping one entry
    per column in page order.
    """
    cols: dict[str, int] = {}
    for i, th in enumerate(row.find_all("th")):
        name = base = text(th).lower()
        n = 1
        while name in cols:
            n += 1
            name = f"{base} {n}"
        cols[name] = i
    return cols


def tracker_id(href: str, pattern: re.Pattern[str]) -> int:
    m = pattern.search(href)
    if not m:
        raise ParseError(f"no torrent ID in link {href!r}")
    return int(m.group(1))


def size(value: str, what: str) -> int:
    try:
        return parse_size(value)
    except UnitError as e:
        raise ParseError(f"{what}: {e}") from e


def session_lifetime(value: str, what: str) -> tuple[int, int]:
    """Peers transfer cell -> (session bytes, lifetime bytes). Empty means nothing yet."""
    if not value.strip():
        return 0, 0
    m = _SESSION_LIFETIME.match(value)
    if not m:
        b = size(value, what)
        return b, b
    return size(m.group(1), what), size(m.group(2), what)


def seed_time(value: str, what: str) -> tuple[int | None, int | None]:
    """Peers seed-time cell -> (seed_time_s, remaining_s); exactly one is set."""
    if not value.strip():
        return None, None
    try:
        seconds, to_go = parse_duration(value)
    except UnitError as e:
        raise ParseError(f"{what}: {e}") from e
    return (None, seconds) if to_go else (seconds, None)


def duration(value: str, what: str) -> int:
    try:
        return parse_duration(value)[0]
    except UnitError as e:
        raise ParseError(f"{what}: {e}") from e


def percent(value: str) -> float | None:
    m = re.search(r"([\d.]+)\s*%?", value)
    return float(m.group(1)) if m and value.strip() else None


def is_truncated(name: str) -> bool:
    return name.endswith("...")


def cell(cells: list[Tag], cols: dict[str, int], *names: str) -> Tag | None:
    """The cell under the first header that exists, among several spellings."""
    for name in names:
        i = cols.get(name)
        if i is not None and i < len(cells):
            return cells[i]
    return None


def require_columns(cols: dict[str, int], *names: str) -> None:
    missing = [n for n in names if n not in cols]
    if missing:
        raise ParseError(f"table is missing columns {missing}; layout changed?")
