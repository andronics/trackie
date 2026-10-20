"""Fetch and parse each tracker's Peers and Hit & Run pages.

Politeness: one request at a time per site with a minimum gap between them,
a browser User-Agent, no retries within a cycle. A failure raises; the
caller keeps its last good snapshot and tries again next cycle.
"""

import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests

from trackie.config import TrackerConfig
from trackie.parsers import HnrPage, ParseError, PeersPage
from trackie.sites import Site

log = logging.getLogger(__name__)

_PROFILE_LINK = re.compile(r'href="/u/(\d+)"')
_PASSWORD_FIELD = re.compile(r"<input[^>]+type=[\"']?password", re.IGNORECASE)
_CLOUDFLARE = ("cf-chl", "challenge-platform", "Just a moment...")


class FetchError(Exception):
    """The site could not be read this cycle: network, server or Cloudflare."""


class AuthError(FetchError):
    """The site answered with a login page: the cookie is missing, wrong or expired."""


@dataclass(frozen=True)
class TrackerPages:
    tracker: str
    user_id: int
    peers: PeersPage
    hnr: HnrPage
    fetched_at: datetime


class SiteClient:
    def __init__(
        self,
        site: Site,
        cfg: TrackerConfig,
        timeout_s: float = 30,
        session: requests.Session | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.site = site
        self.cfg = cfg
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": cfg.user_agent, "Cookie": cfg.cookie})
        self._clock = clock
        self._sleep = sleep
        self._last_request: float | None = None

    def _wait_turn(self) -> None:
        if self._last_request is None:
            return
        gap = self.cfg.request_gap_s + random.uniform(0, self.cfg.request_gap_s / 2)
        wait = self._last_request + gap - self._clock()
        if wait > 0:
            self._sleep(wait)

    def get(self, path: str) -> str:
        self._wait_turn()
        url = f"{self.cfg.base_url}{path}"
        try:
            resp = self.session.get(url, timeout=self.timeout_s)
        except requests.RequestException as e:
            # The exception text can include the URL but never the headers
            raise FetchError(f"{self.site.name}: {type(e).__name__} fetching {path}") from None
        finally:
            self._last_request = self._clock()

        body = resp.text
        final_path = urlparse(resp.url).path.lower()
        if "login" in final_path or _PASSWORD_FIELD.search(body):
            raise AuthError(
                f"{self.site.name}: got a login page for {path}; cookie rejected or expired"
            )
        if any(marker in body for marker in _CLOUDFLARE):
            raise FetchError(f"{self.site.name}: Cloudflare challenge on {path}")
        if resp.status_code >= 400:
            raise FetchError(f"{self.site.name}: HTTP {resp.status_code} for {path}")
        log.debug("%s: fetched %s (%d bytes)", self.site.name, path, len(body))
        return body

    def fetch(self) -> TrackerPages:
        """H&R first: it needs no user ID, and its header reveals the ID for Peers."""
        hnr_html = self.get(self.site.hnr_path)
        hnr = self.site.parse_hnr(hnr_html)

        user_id = self.cfg.user_id
        if user_id is None:
            m = _PROFILE_LINK.search(hnr_html)
            if not m:
                raise ParseError(f"{self.site.name}: no profile link to read the user ID from")
            user_id = int(m.group(1))

        peers = self.site.parse_peers(self.get(self.site.peers_path.format(uid=user_id)))
        return TrackerPages(
            tracker=self.site.key,
            user_id=user_id,
            peers=peers,
            hnr=hnr,
            fetched_at=datetime.now(UTC),
        )
