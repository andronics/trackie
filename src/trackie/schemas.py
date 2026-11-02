"""The HTTP API's documents, as Pydantic models: the OpenAPI schema and the contract.

qbt-rules reads /snapshot, so these shapes are a public interface: a field is added on
purpose and never renamed or removed without a design record. `extra="forbid"` makes the
contract test (tests/unit/test_api.py) fail on a field the models don't declare.

The endpoints don't re-serialise through these models: they send the poller's documents as
trackie always has (snapshot.py, poller.py), byte for byte, and the tests validate those
documents against the models. See docs/design/0001-fastapi.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TorrentRecord(_Model):
    """One tracker torrent: its Peers and Hit & Run rows joined, and its qBittorrent match."""

    tracker: str = Field(description="The tracker's key: `ipt` or `td`.")
    tracker_id: int = Field(description="The torrent's ID on the tracker.")
    name: str
    name_truncated: bool = Field(description="The Peers page cut the name short.")
    status: Literal["required", "satisfied", "hnr"]
    remaining_s: int | None = Field(description="Seeding time still owed; null once met.")
    seed_time_s: int | None = Field(description="Time seeded, shown once the requirement is met.")
    uploaded_b: int
    downloaded_b: int
    ratio: float | None
    gap_b: int | None = Field(description="Hit & Run only: bytes still needed for 1:1.")
    hnr_seed_time_s: int | None = Field(description="Hit & Run only: seeded toward the reset.")
    on_peers: bool
    on_hnr: bool
    seen_at: str = Field(description="When this record was fetched (ISO 8601, UTC).")
    hash: str | None = Field(description="qBittorrent's info hash; null under `unmatched`.")
    match: Literal["exact", "fuzzy"] | None
    match_source: str | None = Field(description="What matched it: an *arr app, prowlarr, name.")


class Account(_Model):
    """One tracker account: the page header plus the site rules trackie applies."""

    ratio: float | None
    uploaded_b: int
    downloaded_b: int
    bonus: float | None
    seeding: int
    leeching: int
    hnr_count: int
    hnr_limit: int
    hnr_grace_s: int
    min_ratio: float
    announce_hosts: list[str]
    seen_at: str


class Snapshot(_Model):
    """Every tracker's last good data. Records with a known hash are under `torrents`."""

    generated_at: str
    fetched_at: dict[str, str] = Field(description="Per tracker: when its data was fetched.")
    accounts: dict[str, Account]
    torrents: dict[str, TorrentRecord] = Field(description="Keyed by qBittorrent info hash.")
    unmatched: list[TorrentRecord]


class TrackerHealth(_Model):
    ok: bool
    has_data: bool
    fetched_at: str | None
    last_attempt: str | None
    last_success: str | None
    last_error: str | None
    error_kind: Literal["auth", "fetch", "parse", "suspect", "error", "config"] | None
    cookie_ok: bool | None = Field(description="false only when the site sent a login page.")
    failures: int
    next_poll: str | None


class Matching(_Model):
    last_run: str | None
    errors: dict[str, str]
    new_last_run: dict[str, int]
    mappings: dict[str, int]
    hosts: dict[str, str]


class Health(_Model):
    """Always 200 while the process is up; `status` says whether every tracker is fine."""

    version: str
    status: Literal["ok", "degraded"]
    trackers: dict[str, TrackerHealth]
    matching: Matching | None = Field(
        default=None, description="Present when a matching source is configured."
    )


class Ready(_Model):
    status: Literal["ready"]
