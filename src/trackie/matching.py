"""Map tracker torrent IDs to qBittorrent hashes.

The trackers never show info hashes, so each tracker ID is matched through,
in order:

  1. *arr grab history  exact  downloadId is the hash, data.guid the tracker ID
  2. Prowlarr history   exact  tracker ID + full release title, matched to the
                               qBittorrent name of a torrent on that tracker
  3. name (+ size)      fuzzy  H&R names are full; Peers names are a truncated
                               prefix, so those also need the downloaded size
                               to agree with the torrent's size

Every mapping is saved the first time it is found. Both histories lose data
(*arr when a series or movie is deleted, Prowlarr after about four weeks), so
mappings are never re-derived from scratch.

Announce hosts are learned from exact matches: a hash known to be on IPT
tells us its qBittorrent tracker host belongs to IPT.
"""

import json
import logging
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from trackie.sites import SITES
from trackie.snapshot import iso
from trackie.sources import Grab, QbtTorrent, SourceError

log = logging.getLogger(__name__)

# A truncated Peers name shorter than this is too weak to match on
MIN_PREFIX = 20
# Tracker-side downloaded bytes vs torrent size: re-downloaded pieces push it
# a little over, never under, for a completed download
SIZE_LOW, SIZE_HIGH = 0.98, 1.15
# An announce host belongs to a tracker when this share of exact matches agree
HOST_MIN_SHARE = 0.9
HOST_MIN_VOTES = 3


class HistorySource(Protocol):
    name: str

    def grabs(self, since: str | None = None) -> list[Grab]: ...


class TorrentSource(Protocol):
    def torrents(self) -> list[QbtTorrent]: ...


def normalise(name: str) -> str:
    """Release names appear with dots, underscores or spaces between words."""
    return re.sub(r"[\s._]+", " ", name.strip().lower()).strip()


@dataclass
class Mapping:
    hash: str
    match: str  # exact | fuzzy
    source: str  # sonarr, radarr, ..., prowlarr, name, name+size
    matched_at: str


@dataclass
class MappingState:
    mappings: dict[str, dict[int, Mapping]] = field(default_factory=dict)
    titles: dict[str, dict[int, str]] = field(default_factory=dict)  # from Prowlarr
    hosts: dict[str, str] = field(default_factory=dict)  # announce host -> tracker
    checkpoints: dict[str, str] = field(default_factory=dict)  # app -> newest date seen

    def to_json(self) -> dict[str, Any]:
        return {
            "version": 1,
            "mappings": {
                t: {str(tid): vars(m) for tid, m in ms.items()} for t, ms in self.mappings.items()
            },
            "titles": {t: {str(tid): v for tid, v in ts.items()} for t, ts in self.titles.items()},
            "hosts": self.hosts,
            "checkpoints": self.checkpoints,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "MappingState":
        return cls(
            mappings={
                t: {int(tid): Mapping(**m) for tid, m in ms.items()}
                for t, ms in data.get("mappings", {}).items()
            },
            titles={
                t: {int(tid): v for tid, v in ts.items()}
                for t, ts in data.get("titles", {}).items()
            },
            hosts=dict(data.get("hosts", {})),
            checkpoints=dict(data.get("checkpoints", {})),
        )


class MappingStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> MappingState:
        try:
            return MappingState.from_json(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return MappingState()
        except (OSError, ValueError, TypeError) as e:
            # Losing mappings is costly, so keep the bad file for inspection
            log.error("unreadable mappings file %s (%s); starting empty", self.path, e)
            self.path.replace(self.path.with_suffix(".corrupt"))
            return MappingState()

    def save(self, state: MappingState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".mappings.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state.to_json(), f)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


@dataclass
class MatchReport:
    ran_at: str | None = None
    errors: dict[str, str] = field(default_factory=dict)
    new: Counter[str] = field(default_factory=Counter)  # by source


class Matcher:
    def __init__(
        self,
        store: MappingStore,
        arr: Sequence[HistorySource] = (),
        prowlarr: HistorySource | None = None,
        qbt: TorrentSource | None = None,
        configured_hosts: dict[str, Iterable[str]] | None = None,
    ) -> None:
        self.store = store
        self.arr = arr
        self.prowlarr = prowlarr
        self.qbt = qbt
        self.configured_hosts = {
            host.lower(): key for key, hosts in (configured_hosts or {}).items() for host in hosts
        }
        self.state = store.load()
        self.report = MatchReport()
        self._pending = self.report

    # --- lookups used by the snapshot -------------------------------------

    def lookup(self, tracker: str, tracker_id: int) -> Mapping | None:
        return self.state.mappings.get(tracker, {}).get(tracker_id)

    def hosts_for(self, tracker: str) -> list[str]:
        hosts = {
            h for h, k in {**self.state.hosts, **self.configured_hosts}.items() if k == tracker
        }
        return sorted(hosts)

    def tracker_for_host(self, host: str | None) -> str | None:
        if host is None:
            return None
        host = host.lower()
        return self.configured_hosts.get(host) or self.state.hosts.get(host)

    # --- refresh ------------------------------------------------------------

    def _set(self, tracker: str, tid: int, hash_: str, match: str, source: str, now: str) -> bool:
        current = self.state.mappings.setdefault(tracker, {}).get(tid)
        if current is not None and (current.match == "exact" or match == "fuzzy"):
            if current.hash != hash_ and match == "exact":
                log.warning(
                    "%s %d: %s says %s, keeping %s", tracker, tid, source, hash_, current.hash
                )
            return False
        self.state.mappings[tracker][tid] = Mapping(hash_, match, source, now)
        self._pending.new[source] += 1
        return True

    def _read_history(self, src: HistorySource) -> list[Grab]:
        grabs = src.grabs(self.state.checkpoints.get(src.name))
        if grabs:
            newest = max(g.date for g in grabs)
            self.state.checkpoints[src.name] = max(newest, self.state.checkpoints.get(src.name, ""))
        return grabs

    def refresh(self, records: dict[str, list[dict[str, Any]]]) -> MatchReport:
        """One matching pass. `records` are each tracker's current snapshot records."""
        now = iso(datetime.now(UTC))
        report = self._pending = MatchReport(ran_at=now)

        # 1. *arr: exact
        for src in self.arr:
            try:
                for g in self._read_history(src):
                    for key, site in SITES.items():
                        tid = site.tracker_id(g.url)
                        if tid is not None and g.hash:
                            self._set(key, tid, g.hash, "exact", src.name, now)
            except SourceError as e:
                report.errors[src.name] = str(e)

        # 2a. Prowlarr: remember titles; they vanish from Prowlarr after ~4 weeks
        if self.prowlarr is not None:
            try:
                for g in self._read_history(self.prowlarr):
                    for key, site in SITES.items():
                        tid = site.tracker_id(g.url)
                        if tid is not None:
                            self.state.titles.setdefault(key, {})[tid] = g.title
            except SourceError as e:
                report.errors[self.prowlarr.name] = str(e)

        torrents: list[QbtTorrent] = []
        if self.qbt is not None:
            try:
                torrents = self.qbt.torrents()
            except SourceError as e:
                report.errors["qbittorrent"] = str(e)

        if torrents:
            self._learn_hosts(torrents)
            self._match_by_name(records, torrents, now)

        self.store.save(self.state)
        if report.new:
            log.info("matching: new mappings %s", dict(report.new))
        self.report = report  # published only once the pass is complete
        return report

    def _learn_hosts(self, torrents: list[QbtTorrent]) -> None:
        by_hash = {t.hash: t.host for t in torrents if t.host}
        votes: dict[str, Counter[str]] = {}
        for key, ms in self.state.mappings.items():
            for m in ms.values():
                if m.match == "exact" and m.hash in by_hash:
                    votes.setdefault(by_hash[m.hash], Counter())[key] += 1
        for host, counter in votes.items():
            (key, n), total = counter.most_common(1)[0], counter.total()
            # Not unanimity: a torrent cross-posted unchanged to both sites has
            # the same hash on each, so the odd vote for the other tracker is normal
            if n >= HOST_MIN_VOTES and n / total >= HOST_MIN_SHARE:
                self.state.hosts[host] = key
            else:
                log.warning("announce host %s has no clear tracker: %s", host, dict(counter))
                self.state.hosts.pop(host, None)

    def _match_by_name(
        self, records: dict[str, list[dict[str, Any]]], torrents: list[QbtTorrent], now: str
    ) -> None:
        for key, recs in records.items():
            claimed = {m.hash for m in self.state.mappings.get(key, {}).values()}
            pool = [
                t
                for t in torrents
                if self.tracker_for_host(t.host) == key and t.hash not in claimed
            ]
            titles = self.state.titles.get(key, {})
            for rec in recs:
                tid = rec["tracker_id"]
                if self.lookup(key, tid) is not None:
                    continue
                found = self._pick(rec, titles.get(tid), pool)
                if found is None:
                    continue
                torrent, match, source = found
                if self._set(key, tid, torrent.hash, match, source, now):
                    pool.remove(torrent)

    @staticmethod
    def _pick(
        rec: dict[str, Any], title: str | None, pool: list[QbtTorrent]
    ) -> tuple[QbtTorrent, str, str] | None:
        def only(cands: list[QbtTorrent]) -> QbtTorrent | None:
            return cands[0] if len(cands) == 1 else None

        # 2b. Prowlarr title: exact name equality
        if title:
            hit = only([t for t in pool if normalise(t.name) == normalise(title)])
            if hit:
                return hit, "exact", "prowlarr"

        name = normalise(rec["name"])
        if not rec["name_truncated"]:
            hit = only([t for t in pool if normalise(t.name) == name])
            return (hit, "fuzzy", "name") if hit else None

        # 3. Truncated Peers name: prefix plus a size that agrees
        prefix = normalise(rec["name"].removesuffix("..."))
        if len(prefix) < MIN_PREFIX:
            return None
        downloaded = rec["downloaded_b"]
        cands = [t for t in pool if normalise(t.name).startswith(prefix)]
        if downloaded > 0:
            cands = [t for t in cands if t.size and SIZE_LOW <= downloaded / t.size <= SIZE_HIGH]
        hit = only(cands)
        return (hit, "fuzzy", "name+size") if hit else None
