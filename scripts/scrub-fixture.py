#!/usr/bin/env python3
"""Scrub a saved tracker page into a committable test fixture.

Detects the account's user ID (from the /u/<id> profile link), its username
(the text of that link) and every public IPv4 address, and replaces them
with fixed placeholders. Nothing personal is hard-coded here: the values are
read from the page itself.

Usage: scripts/scrub-fixture.py RAW_HTML OUT_HTML

Always run scripts/check-personal-data.py on the output before committing.
"""

import ipaddress
import re
import sys
from pathlib import Path

PLACEHOLDER_USER_ID = "1000000"
PLACEHOLDER_USERNAME = "fixtureuser"
# RFC 5737 documentation range
PLACEHOLDER_IP_PREFIX = "192.0.2."

PROFILE_LINK = re.compile(r'href="/u/(\d+)"[^>]*>([^<]+)<')
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")


def scrub(html: str) -> str:
    link = PROFILE_LINK.search(html)
    if not link:
        raise SystemExit("no /u/<id> profile link found; is this a logged-in tracker page?")
    user_id, username = link.group(1), link.group(2).strip()

    html = re.sub(rf"\b{re.escape(user_id)}\b", PLACEHOLDER_USER_ID, html)
    html = re.sub(rf"\b{re.escape(username)}\b", PLACEHOLDER_USERNAME, html, flags=re.IGNORECASE)

    mapping: dict[str, str] = {}

    def replace_ip(m: re.Match[str]) -> str:
        addr = m.group(1)
        try:
            if not ipaddress.IPv4Address(addr).is_global:
                return addr
        except ValueError:
            return addr
        if addr not in mapping:
            mapping[addr] = f"{PLACEHOLDER_IP_PREFIX}{len(mapping) + 1}"
        return mapping[addr]

    return IPV4.sub(replace_ip, html)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src, dst = Path(argv[0]), Path(argv[1])
    dst.write_text(scrub(src.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"scrubbed {src} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
