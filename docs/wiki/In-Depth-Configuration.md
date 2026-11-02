# In-Depth Configuration

Every setting trackie reads, where it can come from, and its default. An annotated example is in the repository at [contrib/trackie.example.yaml](https://github.com/andronics/trackie/blob/main/contrib/trackie.example.yaml).

## Where configuration comes from

Every setting can be given in four places, and the first one that has it wins:

1. `TRACKIE_<KEY>_FILE`: the path of a file holding the value (Docker and Kubernetes secrets)
2. `TRACKIE_<KEY>`: an environment variable
3. the YAML config file: `TRACKIE_CONFIG` or `--config`, default `/etc/trackie/config.yaml`. A missing file is fine.
4. the built-in default

`<KEY>` is the setting's key in upper case, with the dots as underscores: `ipt.cookie` is `TRACKIE_IPT_COOKIE`, `sonarr.api_key` is `TRACKIE_SONARR_API_KEY`.
A value of the wrong type, such as `0.5` or `true` for an integer or a list for a string, is an error that names the setting.
`trackie config` prints the effective value of every setting and where it came from, with secrets masked.
The engine is [interpose](https://github.com/metalayerlab/interpose)'s settings loader; `src/trackie/config.py` declares the settings.

Everything can be set by environment variables alone, as the [Quick Start](Quick-Start) does. A `_FILE` variable that points at a missing or unreadable file stops trackie at startup with a message naming the variable, rather than silently falling through to the next source.

## Settings

Generated from the code: don't edit the table, run `uv run scripts/gen-wiki.py`.

<!-- generated:start settings -->
| Key | Environment variable | Default | Description |
|---|---|---|---|
| `log_level` | `TRACKIE_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `listen.host` | `TRACKIE_LISTEN_HOST` | `0.0.0.0` | Address the HTTP server binds to. |
| `listen.port` | `TRACKIE_LISTEN_PORT` | `8080` | Port the HTTP server listens on. |
| `state_dir` | `TRACKIE_STATE_DIR` | `/var/lib/trackie` | Directory for each tracker's last good data and the ID-to-hash mappings. Unset, and `/config/state` exists (the volume before 0.2), that is used instead. |
| `timeout` | `TRACKIE_TIMEOUT` | `30` | Seconds per HTTP request. |
| `poll.interval` | `TRACKIE_POLL_INTERVAL` | `2700` | Seconds between fetches of each tracker; at least 600. |
| `poll.jitter` | `TRACKIE_POLL_JITTER` | `600` | Up to this many seconds are added to each interval at random. |
| `poll.max_backoff` | `TRACKIE_POLL_MAX_BACKOFF` | `21600` | After failures the interval doubles, up to this many seconds. |
| `ipt.enabled` | `TRACKIE_IPT_ENABLED` | `True` | Fetch IPTorrents. |
| `ipt.cookie` | `TRACKIE_IPT_COOKIE` | *(none)* | The `Cookie` header of a logged-in IPTorrents browser session; required while IPTorrents is enabled. Without it IPTorrents is reported as `error_kind: config` and never fetched. 🔒 Secret: use the `_FILE` variant. |
| `ipt.base_url` | `TRACKIE_IPT_BASE_URL` | `https://iptorrents.com` | The IPTorrents site address. |
| `ipt.user_agent` | `TRACKIE_IPT_USER_AGENT` | `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36` | User-Agent sent to IPTorrents. |
| `ipt.user_id` | `TRACKIE_IPT_USER_ID` | `0` | Your IPTorrents user ID; `0` reads it from the site. |
| `ipt.request_gap` | `TRACKIE_IPT_REQUEST_GAP` | `5` | Minimum seconds between two requests to IPTorrents. |
| `ipt.hnr_limit` | `TRACKIE_IPT_HNR_LIMIT` | `40` | Hit & Run torrents IPTorrents allows before a warning. |
| `ipt.hnr_grace` | `TRACKIE_IPT_HNR_GRACE` | `432000` | Seconds unseeded before a IPTorrents torrent counts as a Hit & Run. |
| `ipt.min_ratio` | `TRACKIE_IPT_MIN_RATIO` | `1.0` | The minimum account ratio IPTorrents requires. |
| `ipt.announce_hosts` | `TRACKIE_IPT_ANNOUNCE_HOSTS` | *(empty list)* | Host names in qBittorrent's tracker URLs that are IPTorrents. Usually unneeded: trackie learns them from exact matches. A list: YAML, or comma-separated. |
| `td.enabled` | `TRACKIE_TD_ENABLED` | `True` | Fetch TorrentDay. |
| `td.cookie` | `TRACKIE_TD_COOKIE` | *(none)* | The `Cookie` header of a logged-in TorrentDay browser session; required while TorrentDay is enabled. Without it TorrentDay is reported as `error_kind: config` and never fetched. 🔒 Secret: use the `_FILE` variant. |
| `td.base_url` | `TRACKIE_TD_BASE_URL` | `https://www.torrentday.com` | The TorrentDay site address. |
| `td.user_agent` | `TRACKIE_TD_USER_AGENT` | `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36` | User-Agent sent to TorrentDay. |
| `td.user_id` | `TRACKIE_TD_USER_ID` | `0` | Your TorrentDay user ID; `0` reads it from the site. |
| `td.request_gap` | `TRACKIE_TD_REQUEST_GAP` | `5` | Minimum seconds between two requests to TorrentDay. |
| `td.hnr_limit` | `TRACKIE_TD_HNR_LIMIT` | `40` | Hit & Run torrents TorrentDay allows before a warning. |
| `td.hnr_grace` | `TRACKIE_TD_HNR_GRACE` | `259200` | Seconds unseeded before a TorrentDay torrent counts as a Hit & Run. |
| `td.min_ratio` | `TRACKIE_TD_MIN_RATIO` | `0.3` | The minimum account ratio TorrentDay requires. |
| `td.announce_hosts` | `TRACKIE_TD_ANNOUNCE_HOSTS` | *(empty list)* | Host names in qBittorrent's tracker URLs that are TorrentDay. Usually unneeded: trackie learns them from exact matches. A list: YAML, or comma-separated. |
| `qbittorrent.url` | `TRACKIE_QBITTORRENT_URL` | *(none)* | qBittorrent's Web UI address; empty: not used. |
| `qbittorrent.username` | `TRACKIE_QBITTORRENT_USERNAME` | *(none)* | qBittorrent user, when it requires a login. |
| `qbittorrent.password` | `TRACKIE_QBITTORRENT_PASSWORD` | *(none)* | qBittorrent password. 🔒 Secret: use the `_FILE` variant. |
| `sonarr.url` | `TRACKIE_SONARR_URL` | *(none)* | The Sonarr address; empty: not used. |
| `sonarr.api_key` | `TRACKIE_SONARR_API_KEY` | *(none)* | The Sonarr API key (read-only use). 🔒 Secret: use the `_FILE` variant. |
| `radarr.url` | `TRACKIE_RADARR_URL` | *(none)* | The Radarr address; empty: not used. |
| `radarr.api_key` | `TRACKIE_RADARR_API_KEY` | *(none)* | The Radarr API key (read-only use). 🔒 Secret: use the `_FILE` variant. |
| `readarr.url` | `TRACKIE_READARR_URL` | *(none)* | The Readarr address; empty: not used. |
| `readarr.api_key` | `TRACKIE_READARR_API_KEY` | *(none)* | The Readarr API key (read-only use). 🔒 Secret: use the `_FILE` variant. |
| `lidarr.url` | `TRACKIE_LIDARR_URL` | *(none)* | The Lidarr address; empty: not used. |
| `lidarr.api_key` | `TRACKIE_LIDARR_API_KEY` | *(none)* | The Lidarr API key (read-only use). 🔒 Secret: use the `_FILE` variant. |
| `prowlarr.url` | `TRACKIE_PROWLARR_URL` | *(none)* | The Prowlarr address; empty: not used. |
| `prowlarr.api_key` | `TRACKIE_PROWLARR_API_KEY` | *(none)* | The Prowlarr API key (read-only use). 🔒 Secret: use the `_FILE` variant. |
<!-- generated:end settings -->

### Trackers

The `ipt.*` and `td.*` settings are the same for each site. A boolean such as `ipt.enabled` takes `true`/`false` (and `1`/`0`, `yes`/`no`, `on`/`off` from the environment).

- **An enabled tracker needs a cookie.** Without one trackie still starts and serves, but never fetches that site: `/health` shows it with `ok: false` and `error_kind: config`. Set the cookie, or `TRACKIE_<SITE>_ENABLED=false`.
- **The site rules** (`hnr_limit`, `hnr_grace`, `min_ratio`) don't change what trackie does: they're passed through into each account record so consumers can compare against them. Update them if a site changes its rules. See [Supported Trackers](Supported-Trackers#site-rules).
- **`announce_hosts`** is a YAML list, or comma-separated in the variable. trackie learns the hosts from exact matches anyway, so it is rarely needed.
- **`base_url`** changes the site address, for a mirror.

### Sources

Where hashes come from. Each app is used only when its URL is set; see [Matching](Matching). qBittorrent is needed for Prowlarr and name matching, and to learn announce hosts; its `username` only when it requires a login from trackie's network. Sonarr and Radarr speak API v3; Readarr, Lidarr and Prowlarr v1.

An app with a URL but no API key stops trackie at startup. With no sources at all, matching is off: every record lands in `unmatched`, and `/health` has no `matching` section.

### Polling

`poll.interval` under 600 seconds is refused: be kind to the trackers. After failures the wait doubles each time, up to `poll.max_backoff`. `timeout` applies to trackers and sources alike. See [Polling and Failures](Polling-and-Failures).

### Storage

**Keep `state_dir` on a volume.** It holds each tracker's last good data and `mappings.json`; losing `mappings.json` loses every mapping whose source history has since been deleted, and those can't be recovered.

When `state_dir` is not set and `/config/state` exists, trackie uses `/config/state`: that is where the image kept its state before 0.2, and where the homelab Kubernetes deployment's volume still is. `trackie config` then shows its source as `default: /config/state exists`.

### Changes in 0.2

trackie moved to interpose's settings engine, which names every variable after its key. The variables kept their names, so an environment-only deployment needs no change. The config file did change:

| Before 0.2 | Now |
|---|---|
| `/config/config.yml` (`CONFIG_DIR`) | `/etc/trackie/config.yaml` (`TRACKIE_CONFIG`) |
| `trackers.ipt.*`, `trackers.td.*` | `ipt.*`, `td.*` |
| `sources.qbittorrent.*`, `sources.sonarr.*`, ... | `qbittorrent.*`, `sonarr.*`, ... |
| `http.timeout` | `timeout` |
| `TRACKIE_MAX_BACKOFF` | `TRACKIE_POLL_MAX_BACKOFF` (the key, `poll.max_backoff`, is unchanged) |
| `trackers.<site>.user_id` unset | `<site>.user_id: 0` (the default) reads it from the site |

Nothing is silently ignored: a file with a `trackers`, `sources` or `http` section, a `/config/config.yml` when no file was named, and `TRACKIE_MAX_BACKOFF` each stop trackie at startup with what to change.

## Secrets

A secret setting is read from all four places, like any other, so nothing stops it being set in the config file or a plain environment variable. Don't: `docker inspect` and `ps` show the variable. Use the `_FILE` variant and mount the value as a file:

- Docker: `TRACKIE_<KEY>_FILE=/run/secrets/<name>` with a secrets file or bind mount
- Kubernetes: a Secret mounted as a volume (SOPS-encrypted in the GitOps repo)

trackie's secrets:

| Setting | Variable to use | Grants |
|---|---|---|
| `ipt.cookie`, `td.cookie` | `TRACKIE_IPT_COOKIE_FILE`, `TRACKIE_TD_COOKIE_FILE` | A logged-in session on the site |
| `sonarr.api_key`, `radarr.api_key`, `readarr.api_key`, `lidarr.api_key`, `prowlarr.api_key` | `TRACKIE_<APP>_API_KEY_FILE` | Full API access to that app (trackie only reads) |
| `qbittorrent.password` | `TRACKIE_QBITTORRENT_PASSWORD_FILE` | qBittorrent's Web UI |

See [Security](Security#secrets) for how they're protected and rotated.

## Examples

**Environment only, with Docker secrets** (the [Quick Start](Quick-Start) and the Kubernetes deployment): no config file at all.

```yaml
environment:
  TRACKIE_IPT_COOKIE_FILE: /run/secrets/ipt_cookie
  TRACKIE_TD_COOKIE_FILE: /run/secrets/td_cookie
  TRACKIE_QBITTORRENT_URL: http://qbittorrent:8080
  TRACKIE_SONARR_URL: http://sonarr:8989
  TRACKIE_SONARR_API_KEY_FILE: /run/secrets/sonarr_api_key
```

**One tracker, slower polling**, in `/etc/trackie/config.yaml`:

```yaml
td:
  enabled: false
poll:
  interval: 3600
ipt:
  min_ratio: 1.0
  hnr_limit: 40
# cookie via TRACKIE_IPT_COOKIE_FILE
```

**A config file for everything but secrets**: copy [contrib/trackie.example.yaml](https://github.com/andronics/trackie/blob/main/contrib/trackie.example.yaml) and edit it.
