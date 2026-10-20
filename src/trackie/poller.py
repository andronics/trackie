"""Fetch each tracker on a slow timer and keep its last good snapshot section.

A failed or suspicious fetch never replaces good data: the snapshot keeps
the previous section and its fetched_at, so consumers see the data age and
can decide for themselves when it is too old to act on.
"""

import logging
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from trackie.config import Config
from trackie.fetch import AuthError, FetchError, SiteClient, TrackerPages
from trackie.matching import Matcher
from trackie.parsers import ParseError
from trackie.sites import SITES
from trackie.snapshot import assemble, iso, tracker_section
from trackie.store import StateStore

log = logging.getLogger(__name__)

# A Peers page that suddenly has no rows is a layout change or an error page
# far more often than a real "nothing seeding"
SUSPECT_DROP_FROM = 5


class SuspectError(Exception):
    """The fetch parsed, but the result is implausible next to the last good one."""


@dataclass
class TrackerState:
    key: str
    section: dict[str, Any] | None = None
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None
    error_kind: str | None = None  # auth | fetch | parse | suspect
    failures: int = 0
    next_poll: datetime | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


def check_plausible(pages: TrackerPages, previous: dict[str, Any] | None) -> None:
    if pages.peers.rows:
        return
    if pages.peers.account.seeding > 0:
        raise SuspectError(
            f"Peers page has no rows but the header says {pages.peers.account.seeding} seeding"
        )
    if previous is not None:
        before = sum(1 for r in previous["records"] if r["on_peers"])
        if before >= SUSPECT_DROP_FROM:
            raise SuspectError(f"Peers rows dropped from {before} to 0")


class Poller:
    def __init__(
        self,
        config: Config,
        store: StateStore,
        client_factory: Callable[[str], SiteClient] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        matcher: Matcher | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.matcher = matcher
        self._match_lock = threading.Lock()
        self._match_due = matcher is not None
        self._now = now
        self._client_factory = client_factory or self._default_client
        self._clients: dict[str, SiteClient] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.states: dict[str, TrackerState] = {}
        for key, cfg in config.trackers.items():
            if cfg.enabled:
                state = TrackerState(key=key, section=store.load(key))
                self.states[key] = state

    def _default_client(self, key: str) -> SiteClient:
        return SiteClient(SITES[key], self.config.trackers[key], timeout_s=self.config.timeout_s)

    def _client(self, key: str) -> SiteClient:
        if key not in self._clients:
            self._clients[key] = self._client_factory(key)
        return self._clients[key]

    def _delay(self, failures: int) -> timedelta:
        base = min(self.config.poll_interval_s * 2**failures, self.config.max_backoff_s)
        return timedelta(seconds=base + random.uniform(0, self.config.poll_jitter_s))

    def poll(self, key: str) -> None:
        """One fetch of one tracker. Never raises: failures are recorded on the state."""
        state = self.states[key]
        started = self._now()
        try:
            pages = self._client(key).fetch()
            check_plausible(pages, state.section)
            section = tracker_section(pages, self.config.trackers[key])
        except Exception as e:  # noqa: BLE001 - one tracker's failure must not stop the loop
            kind = {
                AuthError: "auth",
                FetchError: "fetch",
                ParseError: "parse",
                SuspectError: "suspect",
            }.get(type(e), "error")
            with state.lock:
                state.last_attempt = started
                state.last_error = str(e) if kind != "error" else f"{type(e).__name__}: {e}"
                state.error_kind = kind
                state.failures += 1
                state.next_poll = started + self._delay(state.failures)
            log.warning("%s: %s failure (%d in a row): %s", key, kind, state.failures, e)
            if kind == "error":
                log.exception("%s: unexpected error", key)
            return

        self.store.save(key, section)
        with state.lock:
            state.section = section
            state.last_attempt = started
            state.last_success = started
            state.last_error = None
            state.error_kind = None
            state.failures = 0
            state.next_poll = started + self._delay(0)
        log.info(
            "%s: %d records, %d H&R, ratio %s",
            key,
            len(section["records"]),
            section["account"]["hnr_count"],
            section["account"]["ratio"],
        )

    def run_due(self) -> None:
        now = self._now()
        for key, state in self.states.items():
            if self._stop.is_set():
                return
            if state.next_poll is None or state.next_poll <= now:
                self.poll(key)
                self._match_due = self.matcher is not None
        if self._match_due:
            self.match()

    def match(self) -> None:
        """Match after each poll, so new tracker rows get hashes straight away."""
        if self.matcher is None:
            return
        records = {}
        for key, state in self.states.items():
            with state.lock:
                if state.section is not None:
                    records[key] = state.section["records"]
        try:
            with self._match_lock:
                self.matcher.refresh(records)
        except Exception:  # noqa: BLE001 - matching must never stop polling
            log.exception("matching failed")
        self._match_due = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_due()
            self._stop.wait(30)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="trackie-poller", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def snapshot(self) -> dict[str, Any]:
        sections = {}
        for key, state in self.states.items():
            with state.lock:
                if state.section is not None:
                    sections[key] = state.section
        with self._match_lock:
            return assemble(sections, self._now(), self.matcher)

    def health(self) -> dict[str, Any]:
        trackers: dict[str, Any] = {}
        healthy = True
        for key, state in self.states.items():
            with state.lock:
                ok = state.section is not None and state.error_kind is None
                healthy = healthy and ok
                trackers[key] = {
                    "ok": ok,
                    "has_data": state.section is not None,
                    "fetched_at": state.section["fetched_at"] if state.section else None,
                    "last_attempt": iso(state.last_attempt) if state.last_attempt else None,
                    "last_success": iso(state.last_success) if state.last_success else None,
                    "last_error": state.last_error,
                    "error_kind": state.error_kind,
                    # False only when the site answered with a login page
                    "cookie_ok": None if state.last_attempt is None else state.error_kind != "auth",
                    "failures": state.failures,
                    "next_poll": iso(state.next_poll) if state.next_poll else None,
                }
        result: dict[str, Any] = {
            "status": "ok" if healthy else "degraded",
            "trackers": trackers,
        }
        if self.matcher is not None:
            report = self.matcher.report
            result["matching"] = {
                "last_run": report.ran_at,
                "errors": report.errors,
                "new_last_run": dict(report.new),
                "mappings": {k: len(v) for k, v in self.matcher.state.mappings.items()},
                "hosts": dict(self.matcher.state.hosts),
            }
            if report.errors:
                result["status"] = "degraded"
        return result
