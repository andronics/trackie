# trackie

Scrapes per-torrent and account stats from private trackers (IPTorrents, TorrentDay) and serves them as one JSON snapshot. It is the companion service for [qbt-rules](https://github.com/andronics/qbt-rules): rules can then check that the *tracker* agrees a ratio or seed-time requirement has been met before acting.

Status: early development. qbt-rules integration is deferred until trackie is proven against the live sites.

## What it does

- Polls each tracker's Peers page (live per-torrent seed time, ratio, "to go") and Hit & Run page (failures and the gap still owed) on a slow timer.
- Maps tracker torrent IDs to qBittorrent hashes, using *arr grab history, then Prowlarr history, then name plus size.
- Serves:
  - `GET /snapshot`: `{fetched_at, accounts, torrents}` keyed by torrent hash.
  - `GET /health`: per-tracker fetch status.

## Design

See the design doc: "qbt-rules: Private Tracker Integration Design".

## Data handling

Saved tracker pages contain usernames, user IDs and IP addresses. Never commit raw pages; `data/` and `tests/fixtures/raw/` are git-ignored, and only scrubbed copies belong in `tests/fixtures/`. Cookies and API keys must never be committed or logged.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check src/ tests/ scripts/ && black --check src/ tests/ scripts/ && mypy src/trackie
pytest -m "not live"
python scripts/check-personal-data.py
```

## CI/CD

| Workflow | Runs on | Does |
| --- | --- | --- |
| `ci.yml` | push to `main` and `dev/**`, PRs | personal-data guard, then ruff, black, mypy and pytest on Python 3.11 to 3.13 (all blocking), version consistency |
| `docker-build.yml` | push to `main`, `dev/**`, `v*` tags | builds the image, smoke-tests `/health`, then pushes `linux/amd64` and `linux/arm64` to `ghcr.io/andronics/trackie` |
| `docker-cleanup.yml` | daily | deletes `dev-*` image tags older than 7 days |
| `release.yml` | `v*` tags | checks the tag matches the version files, writes `CHANGELOG.md`, creates the GitHub release |

Image tags: `edge` (main), `dev-<branch>` and `dev-<branch>-<sha>` (dev branches), `X.Y.Z`, `X.Y`, `X` and `latest` (releases).

Feature work goes on `dev/<name>` branches; pushing one publishes a testable image. To release, run `./scripts/bump-version.sh <major|minor|patch>` on `main`, then `git push && git push --tags`. Never tag by hand and never edit `CHANGELOG.md`.

The optional repo secret `FIXTURE_DENYLIST` (one username, user ID or IP per line) makes the personal-data guard also fail on those exact values without them ever appearing in the repo.

## License

Unlicense. See [LICENSE](LICENSE).
