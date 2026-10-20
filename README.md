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

## License

Unlicense. See [LICENSE](LICENSE).
