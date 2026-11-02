# Security

trackie holds the keys to your tracker accounts (session cookies) and read access to your *arr apps (API keys). It also handles pages full of personal data: your username, user ID and home IP address. This page covers what to lock down and what trackie does to keep those things contained.

## Threat model

- **A tracker cookie is your account.** Anyone with it can browse as you, download as you, and change your settings. Losing one is as bad as losing your password, and on some sites worse: a stolen session can get an account banned for "sharing".
- **trackie only reads.** It never posts a form, clicks a button, zaps an H&R or changes anything on a tracker, in qBittorrent or in the *arr apps. A bug in trackie can serve wrong data; it can't delete a torrent.
- **What it serves is low-value but personal.** `/snapshot` contains torrent names, tracker torrent IDs and account stats. Not secrets, but not something to publish either. trackie never includes your user ID, IP address or username in its output.

### Network Exposure

trackie has **no authentication** on any endpoint (`/snapshot`, `/health`, `/readyz`, `/version`, `/openapi.json`). That's deliberate: it's meant to sit on an internal Docker network next to the one or two services that read it.

- Don't add a `ports:` mapping unless you need to reach it from the host, and then bind it to `127.0.0.1` (`"127.0.0.1:8080:8080"`).
- Don't put it behind a public reverse proxy route. If you really need remote access, put authentication in front of it at the proxy.

## Secrets

Every secret can be given three ways; use the first:

```bash
# 1. File (Docker/Compose secret) — preferred
TRACKIE_IPT_COOKIE_FILE=/run/secrets/ipt_cookie

# 2. Environment variable — visible in `docker inspect`; avoid
TRACKIE_IPT_COOKIE='uid=…; pass=…'

# 3. the config file — the file then holds a secret; avoid
```

The same applies to `TRACKIE_<APP>_API_KEY_FILE` and `TRACKIE_QBITTORRENT_PASSWORD_FILE`. See [In-Depth Configuration](In-Depth-Configuration#secrets).

What trackie does with them:

- **Never logs a value.** `trackie config` and the logs show *where* a setting came from (`TRACKIE_IPT_COOKIE_FILE`), never what it is: a secret is held as an interpose `Secret`, which prints as `********`, and is revealed only where it is sent (the `Cookie` header, the `X-Api-Key` header, qBittorrent's login).
- **Never puts them in errors.** A network failure is reported as `ConnectionError fetching /seed_back.php`, not with the request attached. Tests check this.
- **Hides them from `repr`.** Config objects print as `TrackerConfig(key='ipt', enabled=True, …)` with no cookie, so a traceback or debugger can't leak one.
- **API keys go in headers**, never URLs, so they can't end up in a proxy or server access log.

- CI scans every commit with gitleaks, and secrets in history fail the build.

**Rotating:** update the secret file and recreate the container (`docker compose up -d trackie`, or restart the Kubernetes Deployment after updating its Secret). Log out of the tracker in your browser only *after* taking a fresh cookie; logging out usually invalidates the cookie trackie has.

### Personal data in saved pages

Saved tracker pages contain your **username, user ID and home IP**, on nearly every row. The repository is set up so they can't be committed by accident:

- `data/` and `tests/fixtures/raw/` are git-ignored: raw pages go there.
- `scripts/scrub-fixture.py` turns a raw page into a fixture, replacing the user ID, username and every public IP with placeholders (`1000000`, `fixtureuser`, `192.0.2.x`).
- `scripts/check-personal-data.py` (template-base's personal-data guard) runs in CI and **fails the build** if any committed file contains a public IPv4 address.
- `scripts/check-tracker-user-ids.py` fails it on a tracker user ID (`u=<digits>`) other than the placeholder. `scripts/checks.d/50-trackie.sh` runs it, so `sh scripts/checks.sh` and CI's `checks` job both do.
- An optional repository secret lists your real username, IDs and IP (one per line); the guard then also fails on those exact strings, without them ever appearing in the repository. The base guard reads `PERSONAL_DATA_DENYLIST`; trackie's original `FIXTURE_DENYLIST` is still honoured by the *Fixture denylist* workflow (`.github/workflows/fixture-denylist.yml`) until it is renamed.

See [Testing Guide](Testing-Guide#fixtures) for the workflow.

## Hardening

- **Container:** runs as uid 1000 with all capabilities dropped; the compose file adds a read-only root filesystem and `no-new-privileges`. The image holds no secrets and no config: both are mounted.
- **Read-only by design:** no endpoint writes, and no request to a tracker or app changes anything.
- **Supply chain:** dependencies are pinned in `uv.lock` and updated weekly by Dependabot; interpose (pinned to a git tag) by the *Tag check* workflow. GitHub Actions are pinned to commit SHAs.

### Site etiquette

Your account's standing is the thing trackie exists to protect, so it's deliberately gentle:

- Two page loads per tracker per cycle, at least 5 seconds apart.
- A minimum poll interval of 10 minutes is enforced; the default is 45-55.
- Exponential backoff to 6 hours on errors, so an outage or an expired cookie doesn't hammer the site.
- No retries within a cycle, and no fetches triggered by consumers.
- A real browser User-Agent string.

Check your trackers' rules on automated access before enabling it. trackie can't know if a site changes its policy.

## Reporting a vulnerability

Report privately through [GitHub security advisories](https://github.com/andronics/trackie/security/advisories/new), never in a public issue.
