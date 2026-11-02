#!/usr/bin/env python3
"""Fail if any tracked file contains a tracker user ID other than the placeholder.

trackie's own addition to base's personal-data guard (scripts/check-personal-data.py, which
checks public IPs and the denylist): saved tracker pages carry the account's user ID in
`u=<digits>` query parameters, and scripts/scrub-fixture.py replaces it with 1000000.
A line containing "personal-data: ok" is skipped, as in base's guard.

Run by scripts/checks.d/50-trackie.sh, so CI's `checks` job and a local
`sh scripts/checks.sh` both run it. Stdlib only.

    scripts/check-tracker-user-ids.py [PATH ...]    # default: every tracked file
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PLACEHOLDER_USER_ID = "1000000"
USER_ID = re.compile(r"[?&;]u=(\d+)")
ALLOW_MARKER = "personal-data: ok"
SELF = Path(__file__).resolve()


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    return [Path(p) for p in out.stdout.decode().split("\0") if p]


def check(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []  # binary, a directory, or deleted since `git ls-files`
    return [
        f"{path}:{lineno}: user ID u={uid} (use u={PLACEHOLDER_USER_ID})"
        for lineno, line in enumerate(text.splitlines(), 1)
        if ALLOW_MARKER not in line
        for uid in USER_ID.findall(line)
        if uid != PLACEHOLDER_USER_ID
    ]


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or tracked_files()
    problems = [p for path in paths if path.resolve() != SELF for p in check(path)]
    for p in problems:
        print(p)
    if problems:
        print(f"\n{len(problems)} tracker user ID(s). Scrub with scripts/scrub-fixture.py.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
