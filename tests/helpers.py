"""Shared builders for tests."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from trackie.config import Config, TrackerConfig
from trackie.sites import SITES

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def tracker_cfg(key: str, **overrides: object) -> TrackerConfig:
    site = SITES[key]
    cfg = TrackerConfig(
        key=key,
        enabled=True,
        base_url=site.base_url,
        cookie="uid=1000000; pass=SECRETVALUE",
        user_agent="test-agent",
        user_id=None,
        request_gap_s=5,
        hnr_limit=site.hnr_limit,
        hnr_grace_s=site.hnr_grace_s,
        min_ratio=site.min_ratio,
        announce_hosts=(),
    )
    return replace(cfg, **overrides)  # type: ignore[arg-type]


def app_config(state_dir: Path, **overrides: object) -> Config:
    cfg = Config(
        trackers={"ipt": tracker_cfg("ipt"), "td": tracker_cfg("td")},
        timeout_s=30,
        poll_interval_s=2700,
        poll_jitter_s=0,
        max_backoff_s=6 * 3600,
        state_dir=state_dir,
    )
    return replace(cfg, **overrides)  # type: ignore[arg-type]
