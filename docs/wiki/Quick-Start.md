
# Quick Start

From nothing to a working trackie in a few minutes. Everything else is in [In-Depth Configuration](In-Depth-Configuration) and [Deployment](Deployment).

## Prerequisites

- Docker and Docker Compose
- A logged-in browser session on IPTorrents and/or TorrentDay
- qBittorrent with Web UI enabled, on the same Docker network as trackie
- Ideally Sonarr/Radarr and Prowlarr on that network too
- To run from source instead: Python >= 3.13 and [uv](https://docs.astral.sh/uv/)

## Install

The image is `ghcr.io/andronics/trackie` (`linux/amd64`): `:edge` follows `main`, and each release is `:X.Y.Z`, `:X.Y` and `:latest`.

```sh
docker pull ghcr.io/andronics/trackie:edge
# or, from source
uv tool install git+https://github.com/andronics/trackie
```

The rest of this page sets it up with Docker Compose: cookies, API keys, a compose file.

### 1. Get your tracker cookies

trackie signs in with the same session cookie your browser uses. It never sees your password.

1. Log in to the tracker in your browser.
2. Open the developer tools (F12) → **Network** tab, then reload the page.
3. Click the first request to the site and copy the whole **`Cookie`** request header value (everything after `Cookie:` and its space).
4. Save it to a file, one per tracker, readable only by you:

```bash
mkdir -p trackie/secrets && chmod 700 trackie/secrets
printf '%s' 'uid=…; pass=…' > trackie/secrets/ipt_cookie
printf '%s' 'uid=…; pass=…' > trackie/secrets/td_cookie
chmod 600 trackie/secrets/*
```

> **Prowlarr users:** Prowlarr's API won't give the cookie back (it returns `********`), so copy it from the browser as above, even though Prowlarr already has it.

### 2. Get your API keys

For exact matching, trackie reads grab history from your *arr apps and Prowlarr. Each one's API key is under **Settings → General → Security → API Key**. Save each to its own file:

```bash
printf '%s' 'your-sonarr-key'   > trackie/secrets/sonarr_api_key
printf '%s' 'your-radarr-key'   > trackie/secrets/radarr_api_key
printf '%s' 'your-prowlarr-key' > trackie/secrets/prowlarr_api_key
chmod 600 trackie/secrets/*
```

trackie only ever **reads** history. It never changes anything in these apps.

### 3. Create `docker-compose.yml`

```yaml
services:
  trackie:
    image: ghcr.io/andronics/trackie:edge   # or a release: :latest, :X.Y.Z
    container_name: trackie
    restart: unless-stopped
    networks: [media]                  # the network qBittorrent and the *arrs are on
    volumes:
      - ./trackie/state:/var/lib/trackie   # mappings and last good data: keep it on a volume
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

secrets:
  ipt_cookie:       { file: ./trackie/secrets/ipt_cookie }
  td_cookie:        { file: ./trackie/secrets/td_cookie }
  sonarr_api_key:   { file: ./trackie/secrets/sonarr_api_key }
  radarr_api_key:   { file: ./trackie/secrets/radarr_api_key }
  prowlarr_api_key: { file: ./trackie/secrets/prowlarr_api_key }

networks:
  media:
    external: true
```

**Pulling fails with `denied`?** The image's visibility is set separately from the repository's. If it's private, run `docker login ghcr.io` first with a GitHub token that has `read:packages`.

**Secret files unreadable?** The container runs as uid 1000. Compose mounts `file:` secrets with their host ownership and mode, so on a host where your user isn't uid 1000, `chown 1000` the secret files (or relax them to `0640` with a shared group).

**Only use one tracker?** Drop its cookie and add `TRACKIE_TD_ENABLED: "false"` (or `TRACKIE_IPT_ENABLED`). An enabled tracker with no cookie is never fetched: `/health` reports it with `error_kind: config` until you give it one or disable it.

**No `ports:` section:** trackie has no authentication, so keep it on the internal network next to whatever reads it. See [Security](Security#network-exposure).

**qBittorrent needs a login from other containers?** Add `TRACKIE_QBITTORRENT_USERNAME` and `TRACKIE_QBITTORRENT_PASSWORD_FILE`.

## First run

```bash
docker compose up -d trackie
docker compose logs -f trackie
```

**Expected output** (first cycle runs straight away):

```text
INFO trackie.poller: ipt: 180 records, 3 H&R, ratio 1.05
INFO trackie.poller: td: 150 records, 1 H&R, ratio 1.42
INFO trackie.matching: matching: new mappings {'sonarr': 812, 'radarr': 96, 'prowlarr': 2}
```

The first matching pass reads your entire grab history, so it can take a minute. Later passes only read what's new.

### Check it

```bash
# The effective configuration, and where each value came from (secrets masked)
docker exec trackie trackie config

# Is everything healthy?
docker exec trackie python -c "import requests,json; print(json.dumps(requests.get('http://localhost:8080/health').json(), indent=1))"

# How many tracker torrents were matched to qBittorrent?
docker exec trackie python -c "import requests; s=requests.get('http://localhost:8080/snapshot').json(); print(len(s['torrents']), 'matched,', len(s['unmatched']), 'unmatched')"
```

You want `"status": "ok"`, `"cookie_ok": true` for each tracker, and very few unmatched records.

## Next steps

- [How It Works](How-It-Works): what each record means
- [HTTP API Reference](HTTP-API-Reference): the full response format
- [Using with qbt-rules](Using-with-qbt-rules): rules that wait for the tracker
- [In-Depth Configuration](In-Depth-Configuration): every setting
- [Deployment](Deployment): the hardened compose file and Kubernetes
- [Troubleshooting](Troubleshooting) if something doesn't work
