"""Read-only clients for the apps that know which hash belongs to which tracker ID.

  *arr apps   grab history: downloadId (the qBittorrent hash) + data.guid (tracker URL)
  Prowlarr    grab history: tracker URL + release title, no hash
  qBittorrent torrent list: hash, name, size and current announce host

API keys go in the X-Api-Key header and never into URLs, logs or errors.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

PAGE_SIZE = 1000
# Hard stop on paging, far above any real history (Sonarr here: ~15 pages)
MAX_PAGES = 200


class SourceError(Exception):
    """An app could not be read this cycle."""


@dataclass(frozen=True)
class Grab:
    date: str  # ISO 8601, as the app reports it
    url: str  # *arr: data.guid; Prowlarr: data.url
    title: str
    hash: str | None  # lowercase; None for Prowlarr
    app: str


@dataclass(frozen=True)
class QbtTorrent:
    hash: str  # lowercase
    name: str
    size: int
    host: str | None  # hostname of the current tracker, None when not working


class _Api:
    def __init__(self, name: str, url: str, timeout_s: float, session: requests.Session) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session

    def _get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]]) -> Any:
        try:
            resp = self.session.get(f"{self.url}{path}", params=params, timeout=self.timeout_s)
        except requests.RequestException as e:
            raise SourceError(f"{self.name}: {type(e).__name__} fetching {path}") from None
        if resp.status_code in (401, 403):
            raise SourceError(f"{self.name}: HTTP {resp.status_code}; check the API key or login")
        if resp.status_code >= 400:
            raise SourceError(f"{self.name}: HTTP {resp.status_code} for {path}")
        try:
            return resp.json()
        except ValueError:
            raise SourceError(f"{self.name}: {path} did not return JSON") from None


class _HistoryApi(_Api):
    history_path = ""

    def _params(self, page: int) -> list[tuple[str, Any]]:
        return [
            ("page", page),
            ("pageSize", PAGE_SIZE),
            ("sortKey", "date"),
            ("sortDirection", "descending"),
            ("eventType", 1),  # grabbed / releaseGrabbed in every app
        ]

    def _records(self, since: str | None) -> Iterator[dict[str, Any]]:
        """Newest first, stopping once records are older than `since`."""
        for page in range(1, MAX_PAGES + 1):
            body = self._get(self.history_path, self._params(page))
            records = body.get("records") or []
            for rec in records:
                if since is not None and str(rec.get("date", "")) < since:
                    return
                yield rec
            if len(records) < PAGE_SIZE:
                return
        log.warning("%s: stopped paging history after %d pages", self.name, MAX_PAGES)


class ArrClient(_HistoryApi):
    """Sonarr and Radarr (API v3), Readarr and Lidarr (API v1)."""

    def __init__(
        self,
        name: str,
        url: str,
        api_key: str,
        api_version: str,
        timeout_s: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__(name, url, timeout_s, session or requests.Session())
        self.session.headers["X-Api-Key"] = api_key
        self.history_path = f"/api/{api_version}/history"

    def grabs(self, since: str | None = None) -> list[Grab]:
        out = []
        for rec in self._records(since):
            data = rec.get("data") or {}
            download_id = str(rec.get("downloadId") or "")
            if len(download_id) != 40:
                continue  # usenet or a client that is not qBittorrent
            out.append(
                Grab(
                    date=str(rec.get("date", "")),
                    url=str(data.get("guid") or ""),
                    title=str(rec.get("sourceTitle") or ""),
                    hash=download_id.lower(),
                    app=self.name,
                )
            )
        return out


class ProwlarrClient(_HistoryApi):
    history_path = "/api/v1/history"

    def __init__(
        self,
        url: str,
        api_key: str,
        timeout_s: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__("prowlarr", url, timeout_s, session or requests.Session())
        self.session.headers["X-Api-Key"] = api_key

    def grabs(self, since: str | None = None) -> list[Grab]:
        out = []
        for rec in self._records(since):
            data = rec.get("data") or {}
            if not rec.get("successful", True) or not data.get("grabTitle"):
                continue
            out.append(
                Grab(
                    date=str(rec.get("date", "")),
                    url=str(data.get("url") or ""),
                    title=str(data["grabTitle"]),
                    hash=None,
                    app="prowlarr",
                )
            )
        return out


class QbtClient(_Api):
    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        timeout_s: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        super().__init__("qbittorrent", url, timeout_s, session or requests.Session())
        self.username = username
        self.password = password
        self._logged_in = False

    def _login(self) -> None:
        if self._logged_in or not self.username:
            return
        try:
            resp = self.session.post(
                f"{self.url}/api/v2/auth/login",
                data={"username": self.username, "password": self.password},
                timeout=self.timeout_s,
            )
        except requests.RequestException as e:
            raise SourceError(f"qbittorrent: {type(e).__name__} logging in") from None
        if resp.status_code != 200 or resp.text.strip() != "Ok.":
            raise SourceError("qbittorrent: login refused; check username and password")
        self._logged_in = True

    def torrents(self) -> list[QbtTorrent]:
        self._login()
        try:
            rows = self._get("/api/v2/torrents/info", {})
        except SourceError:
            self._logged_in = False  # the session may have expired; log in again next time
            raise
        return [
            QbtTorrent(
                hash=str(t["hash"]).lower(),
                name=str(t.get("name", "")),
                size=int(t.get("total_size") or t.get("size") or 0),
                host=urlparse(t["tracker"]).hostname if t.get("tracker") else None,
            )
            for t in rows
        ]
