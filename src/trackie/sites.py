"""What trackie knows about each tracker: URLs, parsers and default site rules.

Site rules (H&R limit, grace period, minimum ratio) are only defaults here;
config overrides them, so a rule change on a site is a config edit.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from trackie.parsers import HnrPage, PeersPage, ipt, td


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    base_url: str
    peers_path: str  # {uid} is filled in with the account's user ID
    hnr_path: str
    parse_peers: Callable[[str], PeersPage]
    parse_hnr: Callable[[str], HnrPage]
    hnr_limit: int
    hnr_grace_s: int
    min_ratio: float
    # Finds the tracker torrent ID in a details/download URL on any of the
    # site's domains, as stored in *arr history (guid) and Prowlarr (url)
    id_in_url: re.Pattern[str]

    def tracker_id(self, url: str) -> int | None:
        m = self.id_in_url.search(url or "")
        return int(m.group(1)) if m else None


SITES: dict[str, Site] = {
    "ipt": Site(
        key="ipt",
        name="IPTorrents",
        base_url="https://iptorrents.com",
        peers_path="/peers?u={uid}",
        hnr_path="/seeding_required.php",
        parse_peers=ipt.parse_peers,
        parse_hnr=ipt.parse_hnr,
        hnr_limit=40,
        hnr_grace_s=120 * 3600,
        min_ratio=1.0,
        id_in_url=re.compile(
            r"//(?:[\w-]+\.)*iptorrents\.(?:com|me)/(?:t/|download\.php/|details\.php\?id=)(\d+)",
            re.IGNORECASE,
        ),
    ),
    "td": Site(
        key="td",
        name="TorrentDay",
        base_url="https://www.torrentday.com",
        peers_path="/peers?u={uid}",
        hnr_path="/seed_back.php",
        parse_peers=td.parse_peers,
        parse_hnr=td.parse_hnr,
        hnr_limit=40,
        hnr_grace_s=72 * 3600,
        min_ratio=0.3,
        id_in_url=re.compile(
            r"//(?:[\w-]+\.)*(?:torrentday\.(?:com|cool)|tday\.love)"
            r"/(?:details\.php\?id=|download\.php/)(\d+)",
            re.IGNORECASE,
        ),
    ),
}
