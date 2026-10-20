#!/usr/bin/env python3
"""Fail if any tracked file contains personal data from the tracker sites.

Saved tracker pages carry usernames, user IDs and the home IP. Raw copies
belong in git-ignored paths only; committed fixtures must be scrubbed.

Checks every file tracked by git (or the paths given) for:
  - public IPv4 addresses (RFC 5737 documentation ranges, private and
    loopback addresses are allowed, so use 192.0.2.x etc. as placeholders)
  - tracker user-ID query parameters (u=<digits>) other than the placeholder
  - any string listed in FIXTURE_DENYLIST (newline-separated, case-insensitive),
    meant to be supplied from a repo secret so the real values never appear here

Stdlib only, so CI can run it before installing anything.
"""

import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path

PLACEHOLDER_USER_ID = "1000000"
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
USER_ID = re.compile(r"[?&;]u=(\d+)")
SELF = Path(__file__).resolve()


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    return [Path(p) for p in out.stdout.decode().split("\0") if p]


def is_public(addr: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(addr)
    except ValueError:
        return False
    return ip.is_global


def check(path: Path, denylist: list[str]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        return []
    problems = []
    lowered = text.lower()
    for lineno, line in enumerate(text.splitlines(), 1):
        for addr in IPV4.findall(line):
            if is_public(addr):
                problems.append(f"{path}:{lineno}: public IPv4 address")
        for uid in USER_ID.findall(line):
            if uid != PLACEHOLDER_USER_ID:
                problems.append(f"{path}:{lineno}: user ID u={uid} (use u={PLACEHOLDER_USER_ID})")
    for term in denylist:
        if term in lowered:
            problems.append(f"{path}: contains a FIXTURE_DENYLIST entry")
    return problems


def main(argv: list[str]) -> int:
    denylist = [t.strip().lower() for t in os.environ.get("FIXTURE_DENYLIST", "").splitlines()]
    denylist = [t for t in denylist if t]
    paths = [Path(a) for a in argv] or tracked_files()
    problems = []
    for path in paths:
        if path.resolve() != SELF:
            problems.extend(check(path, denylist))
    for p in problems:
        print(p)
    if problems:
        print(f"\n{len(problems)} personal-data finding(s). Scrub before committing.")
        return 1
    print(
        f"No personal data found in {len(paths)} file(s)"
        + (" (denylist active)" if denylist else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
