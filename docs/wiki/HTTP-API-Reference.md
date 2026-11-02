# HTTP API Reference

trackie serves read-only JSON endpoints. There's no authentication and nothing to write, so keep it on an internal network. See [Security](Security#network-exposure).

**Base URL:** `http://trackie:8080` from another container on the same Docker network or Kubernetes namespace (`listen.port`, default `8080`). The live OpenAPI schema is served at `/openapi.json`, and interactive docs at `/docs`.

## Endpoints

Generated from the code: don't edit the table, run `uv run scripts/gen-wiki.py`.

<!-- generated:start http-api -->
| Method | Path | Summary |
|---|---|---|
| `GET` | `/health` | Liveness, with each tracker's fetch status |
| `GET` | `/readyz` | Readiness: 503 unless the poller is running |
| `GET` | `/snapshot` | Every tracker's last good data, keyed by qBittorrent hash |
| `GET` | `/version` | The running version |
<!-- generated:end http-api -->

`/health` (liveness) answers 200 as long as the process runs: the problems are in its body. `/readyz` (readiness) answers 503 while the poller isn't running. Orchestrators should restart on the first and route traffic on the second.

`/snapshot` and `/health` are written exactly as trackie 0.1 wrote them, byte for byte: sorted keys, no spaces, non-ASCII characters escaped as `\uXXXX`, and a trailing newline. The examples below are pretty-printed for reading. Their shapes are pinned by Pydantic models (`src/trackie/schemas.py`) and a contract test with the fields [qbt-rules](Using-with-qbt-rules) reads.

### GET /snapshot

Everything trackie knows, in one call. Designed to be fetched **once per run** by whatever consumes it, not once per torrent.

**Response — `200 OK`:**

```json
{
  "generated_at": "2026-10-20T17:47:02.118Z",
  "fetched_at": {
    "ipt": "2026-10-20T17:46:38.809Z",
    "td": "2026-10-20T17:46:46.051Z"
  },
  "accounts": {
    "td": {
      "ratio": 1.42,
      "uploaded_b": 644245094400,
      "downloaded_b": 453684570429,
      "bonus": 1520.4,
      "seeding": 150,
      "leeching": 0,
      "hnr_count": 1,
      "hnr_limit": 40,
      "hnr_grace_s": 259200,
      "min_ratio": 0.3,
      "announce_hosts": ["sync.td-peers.com", "td.jumbohostpro.eu"],
      "seen_at": "2026-10-20T17:46:46.051Z"
    }
  },
  "torrents": {
    "3f2a9d0c4b1e8a7f6d5c4b3a2918f7e6d5c4c91e": {
      "tracker": "td",
      "tracker_id": 10329334,
      "name": "A Remarkable Place To Die S02E06 1080p TVNZ WEB...",
      "name_truncated": true,
      "status": "required",
      "remaining_s": 82800,
      "seed_time_s": null,
      "uploaded_b": 71617740,
      "downloaded_b": 2297807503,
      "ratio": 0.031,
      "gap_b": null,
      "hnr_seed_time_s": null,
      "on_peers": true,
      "on_hnr": false,
      "seen_at": "2026-10-20T17:46:46.051Z",
      "hash": "3f2a9d0c4b1e8a7f6d5c4b3a2918f7e6d5c4c91e",
      "match": "exact",
      "match_source": "sonarr"
    }
  },
  "unmatched": []
}
```

Every field is described in [Snapshot Fields](Snapshot-Fields).

**Before the first successful fetch** you get the same shape with empty objects and lists. Check `fetched_at` rather than assuming data is there.

**After a failed fetch** you still get the previous data, with the previous `fetched_at`. trackie never blanks good data because one fetch went wrong. **Judge staleness yourself** from `fetched_at`; a sensible consumer treats data older than two or three poll intervals (say 3 hours) as unusable.

### GET /health

How each tracker and the matching sources are doing. Always returns `200` while the server is up (so it works as a Docker healthcheck); the problems are in the body.

**Response — `200 OK`:**

```json
{
  "version": "0.2.0",
  "status": "ok",
  "trackers": {
    "ipt": {
      "ok": true,
      "has_data": true,
      "fetched_at": "2026-10-20T17:46:38.809Z",
      "last_attempt": "2026-10-20T17:46:31.502Z",
      "last_success": "2026-10-20T17:46:31.502Z",
      "last_error": null,
      "error_kind": null,
      "cookie_ok": true,
      "failures": 0,
      "next_poll": "2026-10-20T18:36:15.208Z"
    }
  },
  "matching": {
    "last_run": "2026-10-20T17:47:01.990Z",
    "errors": {},
    "new_last_run": {"prowlarr": 2},
    "mappings": {"ipt": 412, "td": 388},
    "hosts": {"routing.bgp.technology": "ipt", "sync.td-peers.com": "td"}
  }
}
```

| Field | Meaning |
|-------|---------|
| `status` | `ok` when every enabled tracker's last fetch worked and matching had no errors; otherwise `degraded` |
| `trackers.<t>.ok` | Last fetch worked and there is data |
| `trackers.<t>.has_data` | There is *some* data to serve, possibly old |
| `trackers.<t>.error_kind` | `auth` (login page: cookie expired), `fetch` (network, HTTP error, Cloudflare), `parse` (page not as expected), `suspect` (parsed, but implausible), `error` (a bug; see the logs), `config` (enabled, but no cookie configured: never fetched) |
| `trackers.<t>.cookie_ok` | `false` only when the site served a login page. `null` before the first attempt |
| `trackers.<t>.failures` | Failures in a row; drives the backoff |
| `trackers.<t>.next_poll` | When the next fetch is due |
| `matching` | Present when any source is configured. `errors` is keyed by source (`sonarr`, `prowlarr`, `qbittorrent`…); `mappings` counts saved mappings per tracker; `hosts` are the learned announce hosts |

What each `error_kind` means and what to do about it: [Polling and Failures](Polling-and-Failures) and [Troubleshooting](Troubleshooting).

### GET /readyz

`200 {"status": "ready"}` while the poller thread is running; `503 {"detail": "the poller is not running"}` otherwise (it stopped, or the app is still starting). It doesn't depend on the trackers: a site being down is in `/health`, and `/snapshot` keeps serving the last good data.

### GET /version

`{"version": "0.2.0"}`: the running version.

### Quick checks

```bash
# Everything at a glance
curl -s http://trackie:8080/health | jq '{status, trackers: (.trackers | map_values({ok, cookie_ok, error_kind, next_poll}))}'

# All current Hit & Runs, with the gap still owed
curl -s http://trackie:8080/snapshot | jq '[.torrents[], .unmatched[]] | map(select(.status == "hnr")) | map({tracker, name, gap_gb: (.gap_b / 1e9)})'

# Torrents still owing seeding time, soonest first
curl -s http://trackie:8080/snapshot | jq '[.torrents[] | select(.remaining_s != null)] | sort_by(.remaining_s) | map({name, hours: (.remaining_s / 3600)})'
```

No `curl` on the host network? Run the check from inside the container: `docker exec trackie python -c "import requests; print(requests.get('http://localhost:8080/health').text)"`.

## Authentication

None. Every endpoint is read-only and unauthenticated: trackie is meant for an internal network next to its consumers (a Docker network, a Kubernetes namespace), never a published port. If it must be reachable from elsewhere, put forward-auth at the reverse proxy in front of it.

## Errors

Errors are JSON: `{"detail": "<message>"}`. The endpoints take no parameters, so there are few:

| Status | When | What to do |
|---|---|---|
| `404` | An unknown path | Check the URL |
| `405` | A method other than `GET` | Use `GET` |
| `503` | `/readyz` while the poller isn't running; any endpoint in the moment before the app has started | Wait and retry; if `/readyz` stays 503, check the logs and restart |

A tracker failing is never an HTTP error: it's in `/health`, and `/snapshot` keeps the last good data with its `fetched_at`.
