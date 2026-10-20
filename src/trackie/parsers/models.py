"""What the page parsers return. Tracker-neutral: both sites map onto these."""

from dataclasses import dataclass, field
from typing import Literal


class ParseError(Exception):
    """The page is not the expected one: logged out, an error page, or a layout change.

    Never treat this as "no torrents". The caller keeps its last good snapshot.
    """


@dataclass(frozen=True)
class AccountStats:
    """The page header. Cached by the site (about 10 minutes), unlike the rows."""

    ratio: float | None
    uploaded_b: int
    downloaded_b: int
    bonus: float | None
    seeding: int
    leeching: int


@dataclass(frozen=True)
class PeerRow:
    """One row of the Peers page: a torrent the tracker currently sees you on."""

    tracker_id: int
    name: str
    # Peers names are cut short with "..." when long; H&R names are always full
    name_truncated: bool
    role: Literal["seeder", "leecher"]
    uploaded_b: int  # lifetime
    downloaded_b: int  # lifetime
    session_uploaded_b: int
    session_downloaded_b: int
    # Set when the seeding requirement is met: time seeded so far
    seed_time_s: int | None
    # Set while the requirement is still open ("4.9 days to go")
    remaining_s: int | None
    progress_pct: float | None
    client: str
    raw: dict[str, str] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class HnrRow:
    """One row of the Hit & Run page: a torrent stopped before 1:1."""

    tracker_id: int
    name: str
    uploaded_b: int
    downloaded_b: int
    gap_b: int  # bytes still owed to reach 1:1
    seed_time_s: int  # seeded so far toward the reset
    stopped_ago_s: int | None  # IPT only
    clear_cost_points: float | None
    raw: dict[str, str] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class PeersPage:
    account: AccountStats
    rows: list[PeerRow]


@dataclass(frozen=True)
class HnrPage:
    account: AccountStats
    rows: list[HnrRow]
