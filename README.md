# trackie

[![CI](https://github.com/andronics/trackie/actions/workflows/base-ci.yml/badge.svg)](https://github.com/andronics/trackie/actions/workflows/base-ci.yml)
[![Release](https://img.shields.io/github/v/release/andronics/trackie?sort=semver)](https://github.com/andronics/trackie/releases)
[![Image](https://img.shields.io/badge/image-ghcr.io-blue?logo=docker)](https://github.com/andronics/trackie/pkgs/container/trackie)

Scrapes per-torrent and account stats from private trackers (IPTorrents, TorrentDay) and serves them as
one JSON snapshot. It is the companion service for [qbt-rules](https://github.com/andronics/qbt-rules):
rules can check that the *tracker* agrees a ratio or seed-time requirement has been met before acting.

- Polls each tracker's Peers page (live seed time, ratio, "to go") and Hit & Run page on a slow timer.
- Maps tracker torrent IDs to qBittorrent hashes from *arr grab history, then Prowlarr history, then name
  plus size, and saves every mapping.
- Serves `GET /snapshot` (`{generated_at, fetched_at, accounts, torrents, unmatched}`, torrents keyed by
  hash), `GET /health` (per-tracker fetch status) and `GET /readyz`.

## Quick Start

```sh
docker run -d --name trackie -p 127.0.0.1:8080:8080 \
  -v ./state:/var/lib/trackie -v ./secrets:/run/secrets:ro \
  -e TRACKIE_IPT_COOKIE_FILE=/run/secrets/ipt_cookie \
  -e TRACKIE_TD_COOKIE_FILE=/run/secrets/td_cookie \
  -e TRACKIE_QBITTORRENT_URL=http://qbittorrent:8080 \
  ghcr.io/andronics/trackie:edge
curl http://127.0.0.1:8080/health
```

Every setting, and the *arr and Prowlarr sources, are in the wiki's
[In-Depth Configuration](https://github.com/andronics/trackie/wiki/In-Depth-Configuration); the full
walk-through is the [Quick Start](https://github.com/andronics/trackie/wiki/Quick-Start). Keep the state
directory on a volume: it holds every tracker ID to hash mapping ever found, and the histories they came
from don't keep them forever.

## Data handling

Saved tracker pages contain usernames, user IDs and IP addresses. Never commit raw pages: `data/` and
`tests/fixtures/raw/` are git-ignored, and only scrubbed copies belong in `tests/fixtures/`. Cookies and
API keys must never be committed or logged. To add or refresh a test page:

```sh
cp ~/saved-page.html tests/fixtures/raw/ipt_peers.html          # git-ignored
scripts/scrub-fixture.py tests/fixtures/raw/ipt_peers.html tests/fixtures/ipt_peers.html
scripts/check-personal-data.py tests/fixtures/ipt_peers.html    # public IPs, the denylist
scripts/check-tracker-user-ids.py tests/fixtures/ipt_peers.html # u=<id> other than 1000000
```

CI runs both on every tracked file. The optional repository secret `PERSONAL_DATA_DENYLIST` (one
username, user ID or IP per line) makes the guard also fail on those exact values; `FIXTURE_DENYLIST`,
its earlier name, is still read by `fixture-denylist.yml`.

## Documentation

Everything is in the **[wiki](https://github.com/andronics/trackie/wiki)**. Its source is [`docs/wiki/`](docs/wiki/), in this
repository, reviewed with the code.

- [Introduction](https://github.com/andronics/trackie/wiki/Introduction): what it is and how it works
- [In-Depth Configuration](https://github.com/andronics/trackie/wiki/In-Depth-Configuration): every setting
- [Deployment](https://github.com/andronics/trackie/wiki/Deployment): docker, and upgrading from 0.1
- [Using with qbt-rules](https://github.com/andronics/trackie/wiki/Using-with-qbt-rules) and [Snapshot Fields](https://github.com/andronics/trackie/wiki/Snapshot-Fields)
- [Troubleshooting](https://github.com/andronics/trackie/wiki/Troubleshooting) and [FAQ](https://github.com/andronics/trackie/wiki/Frequently-Asked-Questions)
- [Contributing](https://github.com/andronics/trackie/wiki/Contributing) and [Release Process](https://github.com/andronics/trackie/wiki/Release-Process)

## For AI assistants

Built with AI assistants; every change gets human review. **[AGENTS.md](AGENTS.md) and
[.agents/stack.md](.agents/stack.md) are the only instruction files** (stack, commands, rules, definition of
done, docs map). Read them instead of this README.

| Assistant | Entry point |
|---|---|
| Claude Code | [CLAUDE.md](CLAUDE.md) (imports both) + [.claude/settings.json](.claude/settings.json) |
| Codex, Cursor, Copilot coding agent | AGENTS.md, natively ([Copilot](.github/copilot-instructions.md), [Cursor](.cursor/rules/project.mdc) pointers) |
| Gemini CLI | [GEMINI.md](GEMINI.md) (imports both) |
| Chat without repo access | [docs/ai/prompts.md](docs/ai/prompts.md), "Context for a chat assistant" |

Humans: kick-off prompts are in [docs/ai/prompts.md](docs/ai/prompts.md), and the review checklist in
[docs/ai/review-checklist.md](docs/ai/review-checklist.md).

## Development

```sh
uv sync                           # Python >= 3.13, dev tools included
uv run pytest                     # tests (80% coverage floor)
uv run ruff check && uv run mypy  # lint and type check
```

The workflow is: a branch, Conventional Commit PR titles, squash merge. Releases are automated by
release-please. See [Contributing](https://github.com/andronics/trackie/wiki/Contributing).

This project was generated from [template-base](https://github.com/andronics/template-base) and
[template-python](https://github.com/andronics/template-python) (and
[template-container](https://github.com/andronics/template-container) for the image). Template
fixes arrive as a weekly *Template update* PR per template.

## License

Released into the public domain under the [Unlicense](LICENSE).
