from pathlib import Path

import pytest

from trackie.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for var in list(os.environ):
        if var.startswith("TRACKIE_"):
            monkeypatch.delenv(var)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yml"
    path.write_text(text)
    return path


def test_site_defaults_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACKIE_IPT_COOKIE", "uid=1; pass=x")
    monkeypatch.setenv("TRACKIE_TD_COOKIE", "uid=1; pass=y")
    cfg = load_config(tmp_path / "missing.yml")
    ipt, td = cfg.trackers["ipt"], cfg.trackers["td"]
    assert ipt.base_url == "https://iptorrents.com"
    assert (ipt.hnr_limit, ipt.hnr_grace_s, ipt.min_ratio) == (40, 432000, 1.0)
    assert (td.hnr_limit, td.hnr_grace_s, td.min_ratio) == (40, 259200, 0.3)
    assert ipt.user_id is None
    assert cfg.timeout_s == 30


def test_cookie_file_wins_over_env_and_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "ipt_cookie"
    secret.write_text("from-file\n")
    monkeypatch.setenv("TRACKIE_IPT_COOKIE_FILE", str(secret))
    monkeypatch.setenv("TRACKIE_IPT_COOKIE", "from-env")
    path = write(tmp_path, "trackers:\n  ipt: {cookie: from-config}\n  td: {enabled: false}\n")
    assert load_config(path).trackers["ipt"].cookie == "from-file"


def test_config_file_values(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
trackers:
  ipt:
    cookie: c
    user_id: 42
    min_ratio: 0.8
    announce_hosts: [Routing.BGP.Technology, ssl.empirehost.me]
  td:
    enabled: false
http:
  timeout: 10
""",
    )
    cfg = load_config(path)
    ipt = cfg.trackers["ipt"]
    assert ipt.user_id == 42
    assert ipt.min_ratio == 0.8
    assert ipt.announce_hosts == ("routing.bgp.technology", "ssl.empirehost.me")
    assert not cfg.trackers["td"].enabled
    assert cfg.timeout_s == 10


def test_enabled_tracker_without_cookie_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path, "trackers:\n  td: {enabled: false}\n")
    with pytest.raises(ConfigError, match="TRACKIE_IPT_COOKIE_FILE"):
        load_config(path)


def test_unreadable_cookie_file_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRACKIE_IPT_COOKIE_FILE", str(tmp_path / "nope"))
    with pytest.raises(ConfigError, match="TRACKIE_IPT_COOKIE_FILE"):
        load_config(tmp_path / "missing.yml")


def test_repr_hides_cookie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACKIE_IPT_COOKIE", "uid=1; pass=SECRETVALUE")
    monkeypatch.setenv("TRACKIE_TD_ENABLED", "false")
    cfg = load_config(tmp_path / "missing.yml")
    assert "SECRETVALUE" not in repr(cfg)
