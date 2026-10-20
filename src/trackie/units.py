"""Parse the size and duration strings tracker pages display.

Both sites format sizes in binary units (1 KB = 1024 B) and durations as a
decimal count of one unit ("2.1 weeks", "17.0 h"), so values are coarse:
"2.1 weeks" is only accurate to about +/- 8 hours.
"""

import re

_SIZE_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
    "PB": 1024**5,
}

_DURATION_UNITS = {
    "minute": 60,
    "min": 60,
    "hour": 3600,
    "h": 3600,
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
    "year": 365 * 86400,
}

_SIZE = re.compile(r"^\s*([\d.,]+)\s*([KMGTP]?i?B)\s*$", re.IGNORECASE)
_DURATION = re.compile(r"^\s*([\d.,]+)\s*([a-z]+?)s?(\s+to\s+go)?(\s+ago)?\s*$", re.IGNORECASE)


class UnitError(ValueError):
    """A size or duration string in an unrecognised format."""


def parse_size(text: str) -> int:
    """'35.7 MB' -> bytes. Raises UnitError on anything else."""
    m = _SIZE.match(text)
    if not m:
        raise UnitError(f"unrecognised size: {text!r}")
    unit = m.group(2).upper().replace("IB", "B")
    return round(float(m.group(1).replace(",", "")) * _SIZE_UNITS[unit])


def parse_duration(text: str) -> tuple[int, bool]:
    """'4.9 days to go' -> (seconds, to_go). '2.1 weeks' -> (seconds, False).

    A trailing 'ago' is accepted and ignored ('508.1 hours ago').
    """
    m = _DURATION.match(text)
    if not m:
        raise UnitError(f"unrecognised duration: {text!r}")
    unit = m.group(2).lower()
    if unit not in _DURATION_UNITS:
        raise UnitError(f"unrecognised duration unit: {text!r}")
    seconds = round(float(m.group(1).replace(",", "")) * _DURATION_UNITS[unit])
    return seconds, m.group(3) is not None


def parse_number(text: str) -> float | None:
    """'7305.3' or '2,640' -> float; '---', 'Inf.' or '' -> None."""
    try:
        return float(text.strip().replace(",", ""))
    except ValueError:
        return None
