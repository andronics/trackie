"""Configuration: /config/config.yml, overridden by TRACKIE_* environment variables.

Every environment variable also has a _FILE variant that reads the value from
a file (Docker secrets), matching qbt-rules. Resolution order per setting:
VAR_FILE, VAR, config file, default.

Cookies are secrets: supply them as TRACKIE_<SITE>_COOKIE_FILE. Values are
never logged, only where they came from.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from trackie.sites import SITES

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class TrackerConfig:
    key: str
    enabled: bool
    base_url: str
    cookie: str
    user_agent: str
    user_id: int | None  # discovered from the site when not set
    request_gap_s: float
    hnr_limit: int
    hnr_grace_s: int
    min_ratio: float
    announce_hosts: tuple[str, ...]

    def __repr__(self) -> str:
        # Keep the cookie out of logs, tracebacks and debugger output
        return (
            f"TrackerConfig(key={self.key!r}, enabled={self.enabled}, base_url={self.base_url!r})"
        )


@dataclass(frozen=True)
class Config:
    trackers: dict[str, TrackerConfig]
    timeout_s: float


def _nested(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def resolve(env_var: str, data: dict[str, Any], key: str, default: Any = None) -> Any:
    file_var = f"{env_var}_FILE"
    if file_var in os.environ:
        path = Path(os.environ[file_var])
        try:
            log.debug("%s from file %s", key, path)
            return path.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise ConfigError(f"cannot read {file_var} ({path}): {e.strerror}") from e
    if env_var in os.environ:
        log.debug("%s from %s", key, env_var)
        return os.environ[env_var]
    value = _nested(data, key)
    if value is not None:
        log.debug("%s from config file", key)
        return value
    return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _hosts(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = value.split(",")
    return tuple(h.strip().lower() for h in value or () if h.strip())


def load_config(path: Path | None = None) -> Config:
    if path is None:
        path = Path(os.environ.get("CONFIG_DIR", "/config")) / "config.yml"
    data: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ConfigError(f"{path}: top level must be a mapping")
        data = loaded or {}

    trackers: dict[str, TrackerConfig] = {}
    for key, site in SITES.items():
        env = f"TRACKIE_{key.upper()}"
        sect = f"trackers.{key}"
        enabled = _bool(resolve(f"{env}_ENABLED", data, f"{sect}.enabled", True))
        cookie = str(resolve(f"{env}_COOKIE", data, f"{sect}.cookie", "") or "")
        if enabled and not cookie:
            raise ConfigError(
                f"{site.name} is enabled but has no cookie: set {env}_COOKIE_FILE "
                f"or trackers.{key}.enabled: false"
            )
        user_id = resolve(f"{env}_USER_ID", data, f"{sect}.user_id")
        trackers[key] = TrackerConfig(
            key=key,
            enabled=enabled,
            base_url=str(
                resolve(f"{env}_BASE_URL", data, f"{sect}.base_url", site.base_url)
            ).rstrip("/"),
            cookie=cookie,
            user_agent=str(
                resolve(f"{env}_USER_AGENT", data, f"{sect}.user_agent", DEFAULT_USER_AGENT)
            ),
            user_id=int(user_id) if user_id not in (None, "") else None,
            request_gap_s=float(resolve(f"{env}_REQUEST_GAP", data, f"{sect}.request_gap", 5)),
            hnr_limit=int(resolve(f"{env}_HNR_LIMIT", data, f"{sect}.hnr_limit", site.hnr_limit)),
            hnr_grace_s=int(
                resolve(f"{env}_HNR_GRACE", data, f"{sect}.hnr_grace", site.hnr_grace_s)
            ),
            min_ratio=float(resolve(f"{env}_MIN_RATIO", data, f"{sect}.min_ratio", site.min_ratio)),
            announce_hosts=_hosts(resolve(f"{env}_ANNOUNCE_HOSTS", data, f"{sect}.announce_hosts")),
        )
    return Config(
        trackers=trackers,
        timeout_s=float(resolve("TRACKIE_TIMEOUT", data, "http.timeout", 30)),
    )
