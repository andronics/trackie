from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def page():
    """Load a scrubbed saved page by name, e.g. page("ipt_peers")."""

    def load(name: str) -> str:
        return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")

    return load
