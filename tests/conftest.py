"""Shared fixtures."""

from collections.abc import Callable
from pathlib import Path

import pytest

from trackie import config
from trackie.config import ENV_PREFIX

# Scrubbed saved tracker pages (README, "Data handling"): never raw ones
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No test sees the developer's own TRACKIE_* variables, or a /config of this machine's."""
    import os

    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name)
    monkeypatch.setattr(config, "LEGACY_CONFIG_PATH", tmp_path / "no-legacy" / "config.yml")
    monkeypatch.setattr(config, "LEGACY_STATE_DIR", tmp_path / "no-legacy" / "state")


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[..., Path]:
    """Write a config file and return its path."""

    def write(text: str) -> Path:
        path = tmp_path / "config.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    return write


@pytest.fixture
def page() -> Callable[[str], str]:
    """Load a scrubbed saved page by name, e.g. page("ipt_peers")."""

    def load(name: str) -> str:
        return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")

    return load
