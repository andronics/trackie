import pytest

from trackie.units import UnitError, parse_duration, parse_number, parse_size


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0 B", 0),
        ("0.00 kB", 0),
        ("0 KB", 0),
        ("1 KB", 1024),
        ("35.7 MB", round(35.7 * 1024**2)),
        ("2 GB", 2 * 1024**3),
        ("409.52 GB", round(409.52 * 1024**3)),
        ("1.5 TB", round(1.5 * 1024**4)),
        ("1,024 MB", 1024**3),
    ],
)
def test_parse_size(text: str, expected: int) -> None:
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "12", "3 parsecs", "MB"])
def test_parse_size_rejects(text: str) -> None:
    with pytest.raises(UnitError):
        parse_size(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.1 weeks", (round(2.1 * 7 * 86400), False)),
        ("4.9 days to go", (round(4.9 * 86400), True)),
        ("17.0 hours to go", (17 * 3600, True)),
        ("12.0 minutes to go", (720, True)),
        ("0.0 hours", (0, False)),
        ("0.0 h", (0, False)),
        ("1 day", (86400, False)),
        ("508.1 hours ago", (round(508.1 * 3600), False)),
    ],
)
def test_parse_duration(text: str, expected: tuple[int, bool]) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "soon", "3 fortnights", "weeks"])
def test_parse_duration_rejects(text: str) -> None:
    with pytest.raises(UnitError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.410", 0.41),
        ("7305.3", 7305.3),
        ("2,640", 2640.0),
        ("---", None),
        ("Inf.", None),
        ("", None),
    ],
)
def test_parse_number(text: str, expected: float | None) -> None:
    assert parse_number(text) == expected
