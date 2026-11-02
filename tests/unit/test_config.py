"""The project's settings and its own rules.

The engine (lookup order, coercion, ``_FILE``, YAML errors) is interpose's and tested there;
these tests pin what is the project's: the keys and variables, the defaults and the checks.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from interpose.settings import Setting, Settings

from trackie import config
from trackie.config import (
    CONFIG_ENV,
    DEFAULT_CONFIG_PATH,
    ENV_PREFIX,
    LOG_LEVELS,
    SETTINGS,
    ConfigError,
    load_config,
)

TRACKER_FIELDS = (
    "enabled",
    "cookie",
    "base_url",
    "user_agent",
    "user_id",
    "request_gap",
    "hnr_limit",
    "hnr_grace",
    "min_ratio",
    "announce_hosts",
)


def test_keys_and_variables() -> None:
    # Renaming one breaks every deployment that sets it: this list changes only on purpose.
    # These are the variables trackie read before interpose (homelab-k8s sets most of them).
    expected = [
        ("log_level", "TRACKIE_LOG_LEVEL"),
        ("listen.host", "TRACKIE_LISTEN_HOST"),
        ("listen.port", "TRACKIE_LISTEN_PORT"),
        ("state_dir", "TRACKIE_STATE_DIR"),
        ("timeout", "TRACKIE_TIMEOUT"),
        ("poll.interval", "TRACKIE_POLL_INTERVAL"),
        ("poll.jitter", "TRACKIE_POLL_JITTER"),
        ("poll.max_backoff", "TRACKIE_POLL_MAX_BACKOFF"),  # was TRACKIE_MAX_BACKOFF
    ]
    for site in ("ipt", "td"):
        expected += [(f"{site}.{f}", f"TRACKIE_{site.upper()}_{f.upper()}") for f in TRACKER_FIELDS]
    expected += [
        ("qbittorrent.url", "TRACKIE_QBITTORRENT_URL"),
        ("qbittorrent.username", "TRACKIE_QBITTORRENT_USERNAME"),
        ("qbittorrent.password", "TRACKIE_QBITTORRENT_PASSWORD"),
    ]
    for app in ("sonarr", "radarr", "readarr", "lidarr", "prowlarr"):
        expected += [
            (f"{app}.url", f"TRACKIE_{app.upper()}_URL"),
            (f"{app}.api_key", f"TRACKIE_{app.upper()}_API_KEY"),
        ]
    assert [(s.key, s.env) for s in SETTINGS] == expected
    assert CONFIG_ENV == "TRACKIE_CONFIG"
    assert Path("/etc/trackie/config.yaml") == DEFAULT_CONFIG_PATH


def test_secrets() -> None:
    secret = {s.key for s in SETTINGS if s.secret}
    assert secret == {
        "ipt.cookie",
        "td.cookie",
        "qbittorrent.password",
        *(f"{a}.api_key" for a in ("sonarr", "radarr", "readarr", "lidarr", "prowlarr")),
    }


def test_homelab_k8s_variables_are_all_read() -> None:
    # apps/pvr/wave4/trackie.yaml in homelab-k8s: each must still be a setting's variable.
    deployed = [
        "TRACKIE_IPT_COOKIE_FILE",
        "TRACKIE_TD_COOKIE_FILE",
        "TRACKIE_QBITTORRENT_URL",
        "TRACKIE_SONARR_URL",
        "TRACKIE_SONARR_API_KEY_FILE",
        "TRACKIE_RADARR_URL",
        "TRACKIE_RADARR_API_KEY_FILE",
        "TRACKIE_READARR_URL",
        "TRACKIE_READARR_API_KEY_FILE",
        "TRACKIE_LIDARR_URL",
        "TRACKIE_LIDARR_API_KEY_FILE",
        "TRACKIE_PROWLARR_URL",
        "TRACKIE_PROWLARR_API_KEY_FILE",
    ]
    names = {s.env for s in SETTINGS} | {s.env + "_FILE" for s in SETTINGS}
    assert set(deployed) <= names


def test_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.yaml", environ={})
    assert cfg.log_level == "INFO"
    assert (cfg.host, cfg.port) == ("0.0.0.0", 8080)  # noqa: S104
    assert cfg.state_dir == Path("/var/lib/trackie")
    assert set(cfg.sources.values()) == {"default"}
    ipt, td = cfg.trackers["ipt"], cfg.trackers["td"]
    assert ipt.base_url == "https://iptorrents.com"
    assert (ipt.hnr_limit, ipt.hnr_grace_s, ipt.min_ratio) == (40, 432000, 1.0)
    assert (td.hnr_limit, td.hnr_grace_s, td.min_ratio) == (40, 259200, 0.3)
    assert ipt.user_id is None
    assert ipt.request_gap_s == 5
    assert (cfg.timeout_s, cfg.poll_interval_s, cfg.poll_jitter_s) == (30, 2700, 600)
    assert cfg.max_backoff_s == 6 * 3600
    assert (cfg.qbittorrent, cfg.arr_apps, cfg.prowlarr) == (None, (), None)


def test_an_enabled_tracker_without_a_cookie_still_loads(tmp_path: Path) -> None:
    # The poller reports it (error_kind: config) instead: see test_poller.py.
    cfg = load_config(tmp_path / "missing.yaml", environ={})
    assert cfg.trackers["ipt"].enabled
    assert not cfg.trackers["ipt"].cookie


def test_file_overrides_default(write_config: Callable[..., Path]) -> None:
    cfg = load_config(write_config("log_level: debug\n"), environ={})
    assert cfg.log_level == "DEBUG"
    assert cfg.sources["log_level"] == "file"


def test_env_overrides_file(write_config: Callable[..., Path]) -> None:
    path = write_config("log_level: debug\n")
    cfg = load_config(path, environ={"TRACKIE_LOG_LEVEL": "warning"})
    assert cfg.log_level == "WARNING"
    assert cfg.sources["log_level"] == "TRACKIE_LOG_LEVEL"


def test_file_variable_overrides_env(tmp_path: Path) -> None:
    level = tmp_path / "level"
    level.write_text("error\n", encoding="utf-8")
    env = {"TRACKIE_LOG_LEVEL": "warning", "TRACKIE_LOG_LEVEL_FILE": str(level)}
    cfg = load_config(tmp_path / "missing.yaml", environ=env)
    assert cfg.log_level == "ERROR"
    assert cfg.sources["log_level"] == "TRACKIE_LOG_LEVEL_FILE"


def test_cookie_file_wins_over_env_and_config(
    tmp_path: Path, write_config: Callable[..., Path]
) -> None:
    secret = tmp_path / "ipt_cookie"
    secret.write_text("from-file\n", encoding="utf-8")
    env = {"TRACKIE_IPT_COOKIE_FILE": str(secret), "TRACKIE_IPT_COOKIE": "from-env"}
    path = write_config("ipt: {cookie: from-config}\ntd: {enabled: false}\n")
    cfg = load_config(path, environ=env)
    assert cfg.trackers["ipt"].cookie.reveal() == "from-file"
    assert cfg.sources["ipt.cookie"] == "TRACKIE_IPT_COOKIE_FILE"


def test_config_file_values(write_config: Callable[..., Path]) -> None:
    path = write_config(
        """
ipt:
  cookie: c
  user_id: 42
  min_ratio: 0.8
  request_gap: 2.5
  announce_hosts: [Routing.BGP.Technology, ssl.empirehost.me]
td:
  enabled: false
timeout: 10
poll:
  interval: 3600
"""
    )
    cfg = load_config(path, environ={})
    ipt = cfg.trackers["ipt"]
    assert ipt.user_id == 42
    assert ipt.min_ratio == 0.8
    assert ipt.request_gap_s == 2.5
    assert ipt.announce_hosts == ("routing.bgp.technology", "ssl.empirehost.me")
    assert not cfg.trackers["td"].enabled
    assert cfg.timeout_s == 10
    assert cfg.poll_interval_s == 3600


def test_announce_hosts_from_env(tmp_path: Path) -> None:
    env = {"TRACKIE_TD_ANNOUNCE_HOSTS": "A.example, b.example"}
    cfg = load_config(tmp_path / "missing.yaml", environ=env)
    assert cfg.trackers["td"].announce_hosts == ("a.example", "b.example")


def test_poll_interval_has_a_floor(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"poll\.interval: 599 is under 600 seconds"):
        load_config(tmp_path / "missing.yaml", environ={"TRACKIE_POLL_INTERVAL": "599"})


@pytest.mark.parametrize("value", ["fast", "-1", "nan"])
def test_ratio_must_be_a_number(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"ipt\.min_ratio"):
        load_config(tmp_path / "missing.yaml", environ={"TRACKIE_IPT_MIN_RATIO": value})


def test_unreadable_cookie_file_is_an_error(tmp_path: Path) -> None:
    env = {"TRACKIE_IPT_COOKIE_FILE": str(tmp_path / "nope")}
    with pytest.raises(ConfigError, match="TRACKIE_IPT_COOKIE_FILE"):
        load_config(tmp_path / "missing.yaml", environ=env)


def test_repr_hides_secrets(tmp_path: Path) -> None:
    env = {
        "TRACKIE_IPT_COOKIE": "uid=1; pass=SECRETVALUE",
        "TRACKIE_SONARR_URL": "http://sonarr:8989",
        "TRACKIE_SONARR_API_KEY": "k" * 32,
        "TRACKIE_QBITTORRENT_URL": "http://qbt:8080",
        "TRACKIE_QBITTORRENT_PASSWORD": "hunter2hunter2",
    }
    cfg = load_config(tmp_path / "missing.yaml", environ=env)
    for secret in ("SECRETVALUE", "k" * 32, "hunter2hunter2"):
        assert secret not in repr(cfg)
        assert secret not in str(cfg.values)


def test_sources(tmp_path: Path, write_config: Callable[..., Path]) -> None:
    key = tmp_path / "sonarr_key"
    key.write_text("k" * 32, encoding="utf-8")
    env = {
        "TRACKIE_SONARR_API_KEY_FILE": str(key),
        "TRACKIE_PROWLARR_API_KEY": "p" * 32,
        "TRACKIE_READARR_API_KEY": "r" * 32,
    }
    path = write_config(
        """
ipt: {enabled: false}
td: {enabled: false}
qbittorrent: {url: "http://qbt:8080/"}
sonarr: {url: "http://sonarr:8989"}
readarr: {url: "http://readarr:8787"}
prowlarr: {url: "http://prowlarr:9696"}
"""
    )
    cfg = load_config(path, environ=env)
    assert cfg.qbittorrent is not None and cfg.qbittorrent.url == "http://qbt:8080"
    assert [(a.name, a.api_version) for a in cfg.arr_apps] == [("sonarr", "v3"), ("readarr", "v1")]
    assert cfg.arr_apps[0].api_key.reveal() == "k" * 32
    assert cfg.prowlarr is not None and cfg.prowlarr.api_version == "v1"


def test_app_url_without_key_is_an_error(write_config: Callable[..., Path]) -> None:
    path = write_config("radarr: {url: http://r}\n")
    with pytest.raises(ConfigError, match="TRACKIE_RADARR_API_KEY_FILE"):
        load_config(path, environ={})


@pytest.mark.parametrize("name", ["TRACKIE_MAX_BACKOFF", "TRACKIE_MAX_BACKOFF_FILE"])
def test_the_renamed_variable_is_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigError, match=f"{name} is now TRACKIE_POLL_"):
        load_config(tmp_path / "missing.yaml", environ={name: "3600"})


def test_the_old_layout_is_refused(write_config: Callable[..., Path]) -> None:
    path = write_config("trackers:\n  ipt: {cookie: c}\nhttp: {timeout: 10}\n")
    with pytest.raises(ConfigError, match=r"trackers, http are the layout before trackie 0\.2"):
        load_config(path, environ={})


def test_the_old_config_file_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = tmp_path / "config" / "config.yml"
    legacy.parent.mkdir()
    legacy.write_text("poll: {interval: 3600}\n", encoding="utf-8")
    monkeypatch.setattr(config, "LEGACY_CONFIG_PATH", legacy)
    with pytest.raises(
        ConfigError, match=r"is no longer read: move it to /etc/trackie/config\.yaml"
    ):
        load_config(environ={})
    # An explicit file, or TRACKIE_CONFIG, is what the operator asked for
    other = tmp_path / "other.yaml"
    assert load_config(environ={"TRACKIE_CONFIG": str(other)}).poll_interval_s == 2700


def test_the_old_state_volume_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # homelab-k8s mounts its PVC at /config, with the data in /config/state
    legacy = tmp_path / "config" / "state"
    legacy.mkdir(parents=True)
    monkeypatch.setattr(config, "LEGACY_STATE_DIR", legacy)
    cfg = load_config(tmp_path / "missing.yaml", environ={})
    assert cfg.state_dir == legacy
    assert cfg.sources["state_dir"] == f"default: {legacy} exists"
    # Set explicitly, the setting wins
    cfg = load_config(tmp_path / "missing.yaml", environ={"TRACKIE_STATE_DIR": "/srv/t"})
    assert cfg.state_dir == Path("/srv/t")


def test_config_path_from_environment(write_config: Callable[..., Path]) -> None:
    path = write_config("log_level: error\n")
    cfg = load_config(environ={"TRACKIE_CONFIG": str(path)})
    assert cfg.log_level == "ERROR"
    assert cfg.sources["log_level"] == "file"


def test_unreadable_file_variable(tmp_path: Path) -> None:
    env = {"TRACKIE_LOG_LEVEL_FILE": str(tmp_path / "nope")}
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml", environ=env)


def test_invalid_log_level(tmp_path: Path) -> None:
    match = r"log_level: expected one of DEBUG, INFO, WARNING, ERROR, got 'loud'"
    with pytest.raises(ConfigError, match=match):
        load_config(tmp_path / "missing.yaml", environ={"TRACKIE_LOG_LEVEL": "loud"})


def test_level_is_the_declared_spelling(write_config: Callable[..., Path]) -> None:
    # one_of() resolves any case to the spelling LOG_LEVELS declares: the names logging wants.
    assert "INFO" in LOG_LEVELS
    for given in ("info", "Info", "INFO"):
        assert load_config(write_config(f"log_level: {given}\n"), environ={}).log_level == "INFO"
    cfg = load_config(write_config(""), environ={"TRACKIE_LOG_LEVEL": "debug"})
    assert cfg.log_level == "DEBUG"


def test_a_secret_setting(tmp_path: Path) -> None:
    # The pattern for a secret=True setting: read it with secret() and reveal() it where it's used.
    token = Setting("example.token", "", "A token.", secret=True)
    settings = Settings(ENV_PREFIX, (*SETTINGS, token), default_path=DEFAULT_CONFIG_PATH)
    path = tmp_path / "token"
    path.write_text("s3cret\n", encoding="utf-8")
    env = {"TRACKIE_EXAMPLE_TOKEN_FILE": str(path)}
    resolved = settings.resolve(tmp_path / "missing.yaml", env)
    secret = resolved.secret("example.token")
    assert secret.reveal() == "s3cret"
    assert str(secret) == f"{secret}" == "********"
    assert "s3cret" not in repr(secret)
    # str() on a secret setting is refused at load, not sent as ********.
    with pytest.raises(TypeError, match=r"secret setting, not str: use secret\(\) and reveal\(\)"):
        resolved.str("example.token")


def test_top_level_must_be_mapping(write_config: Callable[..., Path]) -> None:
    with pytest.raises(ConfigError, match="the top level must be a mapping"):
        load_config(write_config("- a\n- b\n"), environ={})


def test_empty_file_is_defaults(write_config: Callable[..., Path]) -> None:
    assert load_config(write_config(""), environ={}).log_level == "INFO"


def test_invalid_yaml(write_config: Callable[..., Path]) -> None:
    with pytest.raises(ConfigError, match="cannot parse"):
        load_config(write_config("log_level: [unclosed\n"), environ={})


def test_nested_keys_from_file_and_env(write_config: Callable[..., Path]) -> None:
    cfg = load_config(write_config("listen:\n  port: 9000\n"), environ={})
    assert cfg.port == 9000
    assert cfg.sources["listen.port"] == "file"
    cfg = load_config(write_config(""), environ={"TRACKIE_LISTEN_PORT": "9001"})
    assert cfg.port == 9001
    assert cfg.sources["listen.port"] == "TRACKIE_LISTEN_PORT"


def test_bad_port(write_config: Callable[..., Path]) -> None:
    with pytest.raises(ConfigError, match=r"listen\.port: expected int"):
        load_config(write_config(""), environ={"TRACKIE_LISTEN_PORT": "http"})
    with pytest.raises(ConfigError, match=r"listen\.port: 70000 is not a TCP port"):
        load_config(write_config(""), environ={"TRACKIE_LISTEN_PORT": "70000"})


def test_the_example_config_loads() -> None:
    # contrib/trackie.example.yaml uses only real keys, at their defaults where it says so
    example = Path(__file__).parents[2] / "contrib" / "trackie.example.yaml"
    keys = {f"TRACKIE_{a}_API_KEY": "k" for a in ("SONARR", "RADARR", "PROWLARR")}
    cfg = load_config(example, environ=keys)
    defaults = load_config(example.with_name("missing.yaml"), environ={})
    assert cfg.trackers == defaults.trackers
    assert (cfg.timeout_s, cfg.poll_interval_s, cfg.state_dir) == (30, 2700, defaults.state_dir)
    assert [a.name for a in cfg.arr_apps] == ["sonarr", "radarr"]
