# Troubleshooting

## Diagnostics

- **Effective configuration:** `docker exec trackie trackie config` prints every setting and where it came from (default, file, env var). Secrets are masked.
- **More logging:** `TRACKIE_LOG_LEVEL=DEBUG` (see [Getting more detail](#getting-more-detail)).
- **Ready?** `/readyz` answers 503 if the poller thread isn't running: check the logs, then restart.
- **Container:** `docker logs trackie`, and `docker inspect --format '{{json .State.Health}}' trackie`.

Start with `/health`. It names the tracker or source that's unhappy and why:

```bash
docker exec trackie python -c "import requests,json; print(json.dumps(requests.get('http://localhost:8080/health').json(), indent=1))"
```

Then find the `error_kind` or symptom below.

## Common problems

### `cookie_ok: false` / `error_kind: auth`

**Symptoms:**

```text
WARNING trackie.poller: td: auth failure (1 in a row): TorrentDay: got a login page for /seed_back.php; cookie rejected or expired
```

**Solutions:**

1. **Take a fresh cookie** from a logged-in browser (see [Quick Start](Quick-Start#1-get-your-tracker-cookies)) and update the secret file.
2. **Recreate the container** so it re-reads secrets: `docker compose up -d trackie`.
3. **Don't log out** of the browser session afterwards; logging out usually kills the cookie you just copied.
4. If it fails again straight away, check the cookie is the **whole** header (both `uid=` and `pass=` parts, or whatever the site uses), with no line break at the end.

### `error_kind: fetch`

**Symptoms:** `HTTP 503 for /peers?u=…`, `ConnectionError fetching …`, or `Cloudflare challenge on …`.

**Solutions:**

1. **Is the site up?** Open it in a browser.
2. **Cloudflare challenge:** the site is asking browsers to prove themselves, often during attacks or maintenance. trackie can't solve challenges; it backs off and retries. If it persists for days, try setting `TRACKIE_TD_USER_AGENT` to the exact User-Agent of the browser your cookie came from.
3. **DNS or network:** trackie's container needs outbound internet access. Check with `docker exec trackie python -c "import requests; print(requests.get('https://www.torrentday.com', timeout=10).status_code)"`.

Backoff means the next attempt can be up to 6 hours away; see `next_poll`. Restarting the container retries immediately.

### `error_kind: parse`

**Symptoms:** `no Peers table found`, `table is missing columns ['seed time']; layout changed?`, `unrecognised duration unit: '4.9 fortnights to go'`.

**What it means:** the page loaded, but it isn't laid out the way the parser expects. Usually the site has changed its design.

**Solutions:**

1. Save the page from your browser (**File → Save Page As**, HTML only) into the repository's git-ignored `data/` folder.
2. Open an issue with the error message. **Don't attach the raw page:** it contains your username, user ID and IP. Scrub it first with `scripts/scrub-fixture.py` (see [Testing Guide](Testing-Guide#fixtures)).

Old data keeps being served in the meantime.

### `error_kind: config`

**What it means:** the tracker is enabled but no cookie was configured, so trackie never fetches it (`last_error` names the variable). Set `TRACKIE_<SITE>_COOKIE_FILE` and restart, or disable the tracker with `TRACKIE_<SITE>_ENABLED=false`.

### `error_kind: suspect`

**Symptoms:** `Peers page has no rows but the header says 150 seeding`, or `Peers rows dropped from 180 to 0`.

**What it means:** trackie received a page that parsed but looks wrong, so it kept the previous data. Usually a transient site problem; it clears on the next good fetch. If it persists while your Peers page looks normal in a browser, treat it like a parse error above. See [Polling and Failures](Polling-and-Failures#the-zero-row-guard).

### Lots of unmatched records

**Diagnose:**

```bash
docker exec trackie python -c "
import requests, collections
s = requests.get('http://localhost:8080/snapshot').json()
print(len(s['torrents']), 'matched,', len(s['unmatched']), 'unmatched')
for r in s['unmatched'][:20]: print(r['tracker'], r['tracker_id'], r['status'], r['name'])"
```

**Causes and fixes:**

1. **No *arr sources configured, or a wrong API key:** check `matching.errors` in `/health`.
2. **qBittorrent unreachable or login refused:** `matching.errors.qbittorrent`. Without qBittorrent, only *arr matching runs.
3. **Torrents added by hand** or by an app trackie doesn't read: only name matching can help, and shortened Peers names need a unique prefix of 20+ characters and a matching size.
4. **Announce hosts not learned** (`matching.hosts` empty): name matching only considers torrents on the right tracker. Set `announce_hosts` for each tracker if you have no *arr history to learn from.

### A torrent is missing

1. **Not on the Peers page?** If the tracker doesn't see the torrent announcing, there's no record. Check the torrent's **Trackers** tab in qBittorrent for errors.
2. **In `unmatched`?** Search for its name there (see above).
3. **Just added?** It appears after the next fetch; see `next_poll`.

### `qbittorrent: login refused`

The username or password trackie sent was rejected. If qBittorrent doesn't require a login from trackie's network (check **Options → Web UI → Bypass authentication for clients in whitelisted IP subnets**), remove `TRACKIE_QBITTORRENT_USERNAME` and the password entirely. Otherwise fix the credentials.

### trackie won't start

Startup errors name the setting at fault. A tracker with no cookie is not one of them: it shows as `error_kind: config` above.

| Message | Fix |
|---------|-----|
| `cannot read TRACKIE_TD_COOKIE_FILE (/run/secrets/td_cookie): Permission denied` | The container runs as uid 1000; make the secret file readable by it |
| `sonarr has a URL but no API key` | Set `TRACKIE_SONARR_API_KEY_FILE` |
| `poll.interval: 599 is under 600 seconds; be kind to the trackers` | Raise it; 10 minutes is the floor |
| `... trackers, sources ... the layout before trackie 0.2` | Move the keys: see [In-Depth Configuration](In-Depth-Configuration#changes-in-02) |
| `/config/config.yml is no longer read` | Move it to `/etc/trackie/config.yaml` (or set `TRACKIE_CONFIG`) and update its keys |
| `TRACKIE_MAX_BACKOFF is now TRACKIE_POLL_MAX_BACKOFF` | Rename the variable |
| `ipt.min_ratio: expected a number` (or another setting) | Fix that value; the message names the setting and where it came from |

The command exits with code 2 on a configuration error (see [CLI Reference](CLI-Reference#exit-codes)).

### Getting more detail

```bash
# Debug logging: every tracker page load, and where each setting came from (never its value)
TRACKIE_LOG_LEVEL=DEBUG docker compose up -d trackie
docker compose logs -f trackie
```

Before sharing logs, check them for torrent names you'd rather not post. trackie never logs cookies, API keys, your user ID or your IP.
