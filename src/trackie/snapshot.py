"""Turn fetched pages into the JSON snapshot that /snapshot serves.

Per tracker, the Peers and Hit & Run rows are joined on tracker ID into one
record. Status, in order of precedence:

  hnr        on the Hit & Run list (stays there until the reset or 1:1,
             even if seeding has resumed)
  required   on Peers with time still to go, or still leeching
  satisfied  on Peers with the seeding requirement met

A torrent on neither page is absent: unknown, never assumed satisfied.

Records stay in "unmatched" until matching to qBittorrent hashes exists.
"""

from datetime import UTC, datetime
from typing import Any

from trackie.config import TrackerConfig
from trackie.fetch import TrackerPages
from trackie.parsers import HnrRow, PeerRow


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _record(
    tracker: str, tracker_id: int, peer: PeerRow | None, hnr: HnrRow | None, seen_at: str
) -> dict[str, Any]:
    if hnr is not None:
        status = "hnr"
    elif peer is not None and peer.role == "seeder" and peer.remaining_s is None:
        status = "satisfied"
    else:
        status = "required"

    # Live lifetime totals from Peers when seeding, else from H&R
    if peer is not None:
        uploaded, downloaded = peer.uploaded_b, peer.downloaded_b
    else:
        assert hnr is not None
        uploaded, downloaded = hnr.uploaded_b, hnr.downloaded_b

    return {
        "tracker": tracker,
        "tracker_id": tracker_id,
        # H&R names are always full; Peers names may be cut short
        "name": hnr.name if hnr is not None else peer.name if peer is not None else "",
        "name_truncated": hnr is None and peer is not None and peer.name_truncated,
        "status": status,
        "remaining_s": peer.remaining_s if peer is not None else None,
        "seed_time_s": peer.seed_time_s if peer is not None else None,
        "uploaded_b": uploaded,
        "downloaded_b": downloaded,
        "ratio": round(uploaded / downloaded, 3) if downloaded else None,
        "gap_b": hnr.gap_b if hnr is not None else None,
        "hnr_seed_time_s": hnr.seed_time_s if hnr is not None else None,
        "on_peers": peer is not None,
        "on_hnr": hnr is not None,
        "seen_at": seen_at,
    }


def tracker_section(pages: TrackerPages, cfg: TrackerConfig) -> dict[str, Any]:
    """Everything one fetch of one tracker contributes to the snapshot."""
    seen_at = iso(pages.fetched_at)
    peers = {r.tracker_id: r for r in pages.peers.rows}
    hnrs = {r.tracker_id: r for r in pages.hnr.rows}
    account = pages.peers.account
    return {
        "fetched_at": seen_at,
        "account": {
            "ratio": account.ratio,
            "uploaded_b": account.uploaded_b,
            "downloaded_b": account.downloaded_b,
            "bonus": account.bonus,
            "seeding": account.seeding,
            "leeching": account.leeching,
            # Counted from the live rows, not the site's cached banner
            "hnr_count": len(hnrs),
            "hnr_limit": cfg.hnr_limit,
            "hnr_grace_s": cfg.hnr_grace_s,
            "min_ratio": cfg.min_ratio,
            "announce_hosts": list(cfg.announce_hosts),
            "seen_at": seen_at,
        },
        "records": [
            _record(cfg.key, tid, peers.get(tid), hnrs.get(tid), seen_at)
            for tid in sorted(peers.keys() | hnrs.keys())
        ],
    }


def assemble(sections: dict[str, dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The /snapshot document from each tracker's last good section."""
    return {
        "generated_at": iso(now),
        "fetched_at": {key: s["fetched_at"] for key, s in sections.items()},
        "accounts": {key: s["account"] for key, s in sections.items()},
        "torrents": {},
        "unmatched": [r for s in sections.values() for r in s["records"]],
    }
