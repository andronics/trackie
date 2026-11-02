"""Configuration.

Every setting can come from four places, and the first one that has it wins:

1. ``TRACKIE_<NAME>_FILE``: a file that holds the value (Docker / Kubernetes secrets)
2. ``TRACKIE_<NAME>``: an environment variable
3. the YAML config file (``TRACKIE_CONFIG``, default ``/etc/trackie/config.yaml``)
4. the default in SETTINGS

``<NAME>`` is the dotted key in upper case, with the dots as underscores:
``ipt.cookie`` is ``TRACKIE_IPT_COOKIE``.

The engine (lookup order, strict coercion, ``check=``, ``Secret``) is interpose's
(template-python decision 0003); this module holds the project's settings and its own rules.
Its contract with the template-owned files (``cli.py``, ``scripts/gen-wiki.py``): it exports
SETTINGS (each item has key, env, default, help, secret, is_list), CONFIG_ENV, Config (with
``sources``), ConfigError and ``load_config(path=None, environ=None)``.

The keys are chosen so that each variable keeps the name trackie used before interpose
(``TRACKIE_IPT_COOKIE_FILE``, ``TRACKIE_SONARR_API_KEY_FILE``, ``TRACKIE_POLL_INTERVAL``): the
deployments set those. The one exception, ``TRACKIE_MAX_BACKOFF``, is refused with its new
name. Cookies, API keys and the qBittorrent password are secrets: give them
through the ``_FILE`` variable. Values are never logged; only where each one came from is.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from interpose.secret import Secret
from interpose.settings import (
    ConfigError,
    Setting,
    Settings,
    Value,
    non_negative,
    one_of,
    port,
    positive,
)

from trackie.sites import SITES

__all__ = [
    "ARR_APPS",
    "CONFIG_ENV",
    "DEFAULT_CONFIG_PATH",
    "ENV_PREFIX",
    "LOG_LEVELS",
    "SETTINGS",
    "AppConfig",
    "Config",
    "ConfigError",
    "QbtConfig",
    "TrackerConfig",
    "load_config",
]

ENV_PREFIX = "TRACKIE_"
DEFAULT_CONFIG_PATH = Path("/etc/trackie/config.yaml")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

# Before 0.2 the image kept everything in one /config volume: config.yml and state/. A
# deployment that still mounts it keeps its state there (load_config), and an old config.yml
# is refused with what to change rather than silently ignored.
LEGACY_CONFIG_PATH = Path("/config/config.yml")
LEGACY_STATE_DIR = Path("/config/state")
LEGACY_SECTIONS = ("trackers", "sources", "http")
# The one variable whose name changed with interpose (its key, poll.max_backoff, didn't)
RENAMED = {"TRACKIE_MAX_BACKOFF": "TRACKIE_POLL_MAX_BACKOFF"}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Apps with grab history, and the API version each speaks
ARR_APPS = {"sonarr": "v3", "radarr": "v3", "readarr": "v1", "lidarr": "v1"}
_APP_NAMES = {
    "sonarr": "Sonarr",
    "radarr": "Radarr",
    "readarr": "Readarr",
    "lidarr": "Lidarr",
    "prowlarr": "Prowlarr",
}


def _decimal(value: Value) -> None:
    """A non-negative number written as text (interpose has no float settings)."""
    try:
        number = float(str(value))
    except ValueError:
        raise ValueError(f"expected a number, got {value!r}") from None
    if not number >= 0:  # also rejects nan
        raise ValueError(f"{value!r} is not a non-negative number")


def _at_least_600(value: Value) -> None:
    if isinstance(value, int) and value < 600:
        raise ValueError(f"{value} is under 600 seconds; be kind to the trackers")


def _tracker_settings() -> list[Setting]:
    out: list[Setting] = []
    for key, site in SITES.items():
        n = site.name
        out += [
            Setting(f"{key}.enabled", True, f"Fetch {n}."),
            Setting(
                f"{key}.cookie",
                "",
                f"The `Cookie` header of a logged-in {n} browser session; required while "
                f"{n} is enabled. Without it {n} is reported as `error_kind: config` and never "
                "fetched.",
                secret=True,
            ),
            Setting(f"{key}.base_url", site.base_url, f"The {n} site address."),
            Setting(f"{key}.user_agent", DEFAULT_USER_AGENT, f"User-Agent sent to {n}."),
            Setting(
                f"{key}.user_id",
                0,
                f"Your {n} user ID; `0` reads it from the site.",
                check=non_negative,
            ),
            Setting(
                f"{key}.request_gap",
                "5",
                f"Minimum seconds between two requests to {n}.",
                check=_decimal,
            ),
            Setting(
                f"{key}.hnr_limit",
                site.hnr_limit,
                f"Hit & Run torrents {n} allows before a warning.",
                check=non_negative,
            ),
            Setting(
                f"{key}.hnr_grace",
                site.hnr_grace_s,
                f"Seconds unseeded before a {n} torrent counts as a Hit & Run.",
                check=non_negative,
            ),
            Setting(
                f"{key}.min_ratio",
                f"{site.min_ratio}",
                f"The minimum account ratio {n} requires.",
                check=_decimal,
            ),
            Setting(
                f"{key}.announce_hosts",
                "",
                f"Host names in qBittorrent's tracker URLs that are {n}. Usually unneeded: "
                "trackie learns them from exact matches.",
                is_list=True,
            ),
        ]
    return out


def _source_settings() -> list[Setting]:
    out = [
        Setting("qbittorrent.url", "", "qBittorrent's Web UI address; empty: not used."),
        Setting("qbittorrent.username", "", "qBittorrent user, when it requires a login."),
        Setting("qbittorrent.password", "", "qBittorrent password.", secret=True),
    ]
    for name in (*ARR_APPS, "prowlarr"):
        app = _APP_NAMES[name]
        out += [
            Setting(f"{name}.url", "", f"The {app} address; empty: not used."),
            Setting(f"{name}.api_key", "", f"The {app} API key (read-only use).", secret=True),
        ]
    return out


SETTINGS = Settings(
    ENV_PREFIX,
    (
        Setting(
            "log_level",
            "INFO",
            "Log level: `DEBUG`, `INFO`, `WARNING` or `ERROR`.",
            check=one_of(*LOG_LEVELS),
        ),
        Setting("listen.host", "0.0.0.0", "Address the HTTP server binds to."),  # noqa: S104
        Setting("listen.port", 8080, "Port the HTTP server listens on.", check=port),
        Setting(
            "state_dir",
            "/var/lib/trackie",
            "Directory for each tracker's last good data and the ID-to-hash mappings. Unset, "
            "and `/config/state` exists (the volume before 0.2), that is used instead.",
        ),
        Setting("timeout", 30, "Seconds per HTTP request.", check=positive),
        Setting(
            "poll.interval",
            45 * 60,
            "Seconds between fetches of each tracker; at least 600.",
            check=_at_least_600,
        ),
        Setting(
            "poll.jitter",
            10 * 60,
            "Up to this many seconds are added to each interval at random.",
            check=non_negative,
        ),
        Setting(
            "poll.max_backoff",
            6 * 3600,
            "After failures the interval doubles, up to this many seconds.",
            check=positive,
        ),
        *_tracker_settings(),
        *_source_settings(),
    ),
    default_path=DEFAULT_CONFIG_PATH,
)
CONFIG_ENV = SETTINGS.config_env


@dataclass(frozen=True)
class TrackerConfig:
    key: str
    enabled: bool
    base_url: str
    cookie: Secret
    user_agent: str
    user_id: int | None  # discovered from the site when not set
    request_gap_s: float
    hnr_limit: int
    hnr_grace_s: int
    min_ratio: float
    announce_hosts: tuple[str, ...]

    def __repr__(self) -> str:
        return (
            f"TrackerConfig(key={self.key!r}, enabled={self.enabled}, base_url={self.base_url!r})"
        )


@dataclass(frozen=True)
class AppConfig:
    """An *arr app or Prowlarr: read-only API access."""

    name: str
    url: str
    api_key: Secret
    api_version: str

    def __repr__(self) -> str:
        return f"AppConfig(name={self.name!r}, url={self.url!r})"


@dataclass(frozen=True)
class QbtConfig:
    url: str
    username: str
    password: Secret

    def __repr__(self) -> str:
        return f"QbtConfig(url={self.url!r}, username={'set' if self.username else 'unset'})"


@dataclass(frozen=True)
class Config:
    trackers: dict[str, TrackerConfig]
    timeout_s: float
    poll_interval_s: float
    poll_jitter_s: float
    max_backoff_s: float
    state_dir: Path
    qbittorrent: QbtConfig | None = None
    arr_apps: tuple[AppConfig, ...] = ()
    prowlarr: AppConfig | None = None
    log_level: str = "INFO"
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8080
    # Setting key -> where its value came from ("default", "file", an env var name).
    sources: Mapping[str, str] = field(default_factory=dict)
    # Setting key -> its value, for `trackie config` (a secret stays a Secret).
    values: Mapping[str, object] = field(default_factory=dict)


def _check_layout(path: Path) -> None:
    """Refuse a pre-0.2 config file: its keys would be silently ignored."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return  # interpose has already reported anything that matters
    old = [s for s in LEGACY_SECTIONS if isinstance(data, dict) and s in data]
    if old:
        raise ConfigError(
            f"{path}: {', '.join(old)} {'is' if len(old) == 1 else 'are'} the layout before "
            "trackie 0.2: trackers.<site>.* is now <site>.*, sources.<app>.* is <app>.*, and "
            "http.timeout is timeout (see the wiki's In-Depth-Configuration page)"
        )


def load_config(path: Path | None = None, environ: Mapping[str, str] | None = None) -> Config:
    """Load the configuration. A missing config file is not an error: defaults apply."""
    env = os.environ if environ is None else environ
    if path is None and CONFIG_ENV not in env and LEGACY_CONFIG_PATH.is_file():
        raise ConfigError(
            f"{LEGACY_CONFIG_PATH} is no longer read: move it to {DEFAULT_CONFIG_PATH} (or set "
            f"{CONFIG_ENV}) and update its keys (see the wiki's In-Depth-Configuration page)"
        )
    for was, now in RENAMED.items():
        for suffix in ("", "_FILE"):
            if was + suffix in env:
                raise ConfigError(f"{was}{suffix} is now {now}{suffix}")
    r = SETTINGS.resolve(path, env)
    _check_layout(path or Path(env.get(CONFIG_ENV, str(DEFAULT_CONFIG_PATH))))
    sources = dict(r.sources)
    values: dict[str, object] = dict(r.values)

    state_dir = Path(r.str("state_dir"))
    if sources["state_dir"] == "default" and LEGACY_STATE_DIR.is_dir():
        state_dir = LEGACY_STATE_DIR
        sources["state_dir"] = f"default: {LEGACY_STATE_DIR} exists"
        values["state_dir"] = str(state_dir)

    trackers = {
        key: TrackerConfig(
            key=key,
            enabled=r.bool(f"{key}.enabled"),
            base_url=r.str(f"{key}.base_url").rstrip("/"),
            cookie=r.secret(f"{key}.cookie"),
            user_agent=r.str(f"{key}.user_agent"),
            user_id=r.int(f"{key}.user_id") or None,
            request_gap_s=float(r.str(f"{key}.request_gap")),
            hnr_limit=r.int(f"{key}.hnr_limit"),
            hnr_grace_s=r.int(f"{key}.hnr_grace"),
            min_ratio=float(r.str(f"{key}.min_ratio")),
            announce_hosts=tuple(h.lower() for h in r.list(f"{key}.announce_hosts") if h),
        )
        for key in SITES
    }

    def app(name: str, api_version: str) -> AppConfig | None:
        url = r.str(f"{name}.url")
        if not url:
            return None
        api_key = r.secret(f"{name}.api_key")
        if not api_key:
            raise ConfigError(
                f"{name} has a URL but no API key: set {ENV_PREFIX}{name.upper()}_API_KEY_FILE"
            )
        return AppConfig(name, url.rstrip("/"), api_key, api_version)

    qbt_url = r.str("qbittorrent.url")
    return Config(
        trackers=trackers,
        timeout_s=r.int("timeout"),
        poll_interval_s=r.int("poll.interval"),
        poll_jitter_s=r.int("poll.jitter"),
        max_backoff_s=r.int("poll.max_backoff"),
        state_dir=state_dir,
        qbittorrent=(
            QbtConfig(
                url=qbt_url.rstrip("/"),
                username=r.str("qbittorrent.username"),
                password=r.secret("qbittorrent.password"),
            )
            if qbt_url
            else None
        ),
        arr_apps=tuple(a for name, v in ARR_APPS.items() if (a := app(name, v)) is not None),
        prowlarr=app("prowlarr", "v1"),
        log_level=r.str("log_level"),
        host=r.str("listen.host"),
        port=r.int("listen.port"),
        sources=sources,
        values=values,
    )
