# trackie

Scrapes per-torrent and account stats from private trackers (IPTorrents, TorrentDay) and serves them as one JSON snapshot. It is the companion service for [qbt-rules](https://github.com/andronics/qbt-rules): rules can then check that the *tracker* agrees a ratio or seed-time requirement has been met before acting.

Status: early development. qbt-rules integration is deferred until trackie is proven against the live sites.

## What it does

- Polls each tracker's Peers page (live per-torrent seed time, ratio, "to go") and Hit & Run page (failures and the gap still owed) on a slow timer.
- Maps tracker torrent IDs to qBittorrent hashes, using *arr grab history, then Prowlarr history, then name plus size, and saves every mapping. Learns which qBittorrent announce hosts belong to which tracker from the exact matches.
- Serves:
  - `GET /snapshot`: `{fetched_at, accounts, torrents}` keyed by torrent hash.
  - `GET /health`: per-tracker fetch status.

## Running

```yaml
services:
  trackie:
    image: ghcr.io/andronics/trackie:edge
    restart: unless-stopped
    networks: [pvr_stack]          # same network as qBittorrent and the *arr apps
    volumes:
      - ./trackie:/config          # config.yml, plus state/ (last good data, mappings)
    environment:
      TRACKIE_IPT_COOKIE_FILE: /run/secrets/ipt_cookie
      TRACKIE_TD_COOKIE_FILE: /run/secrets/td_cookie
      TRACKIE_QBITTORRENT_URL: http://qbittorrent:8080
      TRACKIE_SONARR_URL: http://sonarr:8989
      TRACKIE_SONARR_API_KEY_FILE: /run/secrets/sonarr_api_key
      TRACKIE_RADARR_URL: http://radarr:7878
      TRACKIE_RADARR_API_KEY_FILE: /run/secrets/radarr_api_key
      TRACKIE_PROWLARR_URL: http://prowlarr:9696
      TRACKIE_PROWLARR_API_KEY_FILE: /run/secrets/prowlarr_api_key
    secrets: [ipt_cookie, td_cookie, sonarr_api_key, radarr_api_key, prowlarr_api_key]
```

Every setting is in [`config/config.example.yml`](config/config.example.yml). Readarr and Lidarr work the same way (`TRACKIE_READARR_*`, `TRACKIE_LIDARR_*`). The port, 8080, is only needed on the Docker network.

Keep `/config/state/mappings.json` on a volume: it holds every tracker ID to hash mapping ever found, and the histories it came from do not keep them forever.

## Design

See the design doc: "qbt-rules: Private Tracker Integration Design".

## Data handling

Saved tracker pages contain usernames, user IDs and IP addresses. Never commit raw pages; `data/` and `tests/fixtures/raw/` are git-ignored, and only scrubbed copies belong in `tests/fixtures/`. Cookies and API keys must never be committed or logged.

To add or refresh a test page:

```sh
cp ~/saved-page.html tests/fixtures/raw/ipt_peers.html          # git-ignored
scripts/scrub-fixture.py tests/fixtures/raw/ipt_peers.html tests/fixtures/ipt_peers.html
scripts/check-personal-data.py tests/fixtures/ipt_peers.html
```

`scrub-fixture.py` finds the account's user ID, username and every public IP in the page itself and swaps in placeholders (`1000000`, `fixtureuser`, `192.0.2.x`).

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
| `docker-build.yml` | push to `main`, `dev/**`, `v*` tags | builds the image, smoke-tests `/health`, then pushes `linux/amd64` (all cluster nodes are amd64) to `ghcr.io/andronics/trackie` |
| `docker-cleanup.yml` | daily | deletes `dev-*` image tags older than 7 days |
| `release.yml` | `v*` tags | checks the tag matches the version files, writes `CHANGELOG.md`, creates the GitHub release |

Image tags: `edge` (main), `dev-<branch>` and `dev-<branch>-<sha>` (dev branches), `X.Y.Z`, `X.Y`, `X` and `latest` (releases).

Feature work goes on `dev/<name>` branches; pushing one publishes a testable image. To release, run `./scripts/bump-version.sh <major|minor|patch>` on `main`, then `git push && git push --tags`. Never tag by hand and never edit `CHANGELOG.md`.

The optional repo secret `FIXTURE_DENYLIST` (one username, user ID or IP per line) makes the personal-data guard also fail on those exact values without them ever appearing in the repo.

## License

Unlicense. See [LICENSE](LICENSE).
