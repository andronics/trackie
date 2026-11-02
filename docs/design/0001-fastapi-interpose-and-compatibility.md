# 0001: FastAPI, interpose settings, and what stays compatible

<!-- Add a line for this record to the index in docs/design/README.md (CI checks). -->

Status: Implemented
Date: 2026-11-02
Authors: Stephen Cox

## Context

trackie moves onto template-base, template-python (`kind: service`) and template-container. The
service template is FastAPI on uvicorn only (template-python decision 0004), and its `config.py` is a
thin layer on interpose's settings engine (decision 0003). trackie was Flask on gunicorn, with its own
settings engine, a poller thread started when the app was created, and one `/config` volume holding
`config.yml` and `state/`.

Two clients must not notice: qbt-rules reads `GET /snapshot` once per run (`qbt_rules/trackie.py`), and
homelab-k8s (`apps/pvr/wave4/trackie.yaml`) runs the image as uid 1000 on port 8080 with a TCP readiness
probe, a PVC at `/config` (state in `/config/state`, no `config.yml`) and only `TRACKIE_*` variables.

## Decision

**HTTP API.** The same paths and methods. `/snapshot` and `/health` send the poller's documents exactly
as Flask's `jsonify` did: sorted keys, compact separators, non-ASCII escaped, a trailing newline
(`CompatJSONResponse`). Their Pydantic models (`schemas.py`, `extra="forbid"`) give the OpenAPI schema
and the generated wiki table; the endpoints don't re-serialise through them, since that orders keys by
model, writes UTF-8 and may coerce types (an int in a float field becomes `1.0`): the bytes would drift. Instead
the tests validate the real documents against the models in strict mode, and pin the fields and JSON
types qbt-rules reads. New: `GET /readyz` (503 unless the poller thread is alive) and `GET /version`.
`/health` stays the liveness path (`health_path: /health`): always 200, its body unchanged.

**The poller** is built, started and stopped in the FastAPI lifespan, never at app creation. An app
built with a poller (tests) leaves it alone.

**A missing cookie is no longer fatal.** An enabled tracker without one is reported (`error_kind:
config`, `ok: false`, its `last_error` naming the variable) and never fetched. The image then starts
with no configuration, which template-container's smoke test needs, and a half-configured deployment
still serves the other tracker.

**Settings** are interpose `Setting`s. interpose names a variable from its key, so the keys follow the
variables trackie already had: `ipt.cookie` is `TRACKIE_IPT_COOKIE`, `sonarr.api_key` is
`TRACKIE_SONARR_API_KEY`, `timeout` is `TRACKIE_TIMEOUT`. Every variable keeps its name except
`TRACKIE_MAX_BACKOFF`, now `TRACKIE_POLL_MAX_BACKOFF` (the key `poll.max_backoff` didn't change); the old
name is a `ConfigError` that names the new one. Cookies, API keys and the qBittorrent password are
`secret=True`, held as `Secret` and revealed only where they go into a request header. interpose has
no float settings: ratios and the request gap are text settings with a number check.

**Files.** The config file is `/etc/trackie/config.yaml` (`TRACKIE_CONFIG`) and the state directory
`/var/lib/trackie`, as the template's Dockerfile and compose file expect. A YAML file in the old layout
(`trackers:`, `sources:`, `http:`) is refused, as is an old `/config/config.yml` when no config path is
given: either would otherwise be silently ignored. With `state_dir` unset and `/config/state` present,
that directory is used, so the homelab deployment keeps its data with no manifest change.

## Alternatives considered

- **Let Pydantic serialise the responses.** Typed end to end, but the bytes change (float fields, key
  order, `ensure_ascii`); qbt-rules would cope, but nothing would show that nothing changed.
- **Keep trackie's own settings engine.** Decision 0003 allows it, but the template's `config`
  command, wiki generator and tests then cover an engine trackie must maintain alone.
- **Keep the old YAML layout** by translating it before interpose reads it: a second parser for one
  release's worth of files, when no known deployment has a `config.yml`.
- **Default `state_dir` to `/config/state`.** No fallback rule, but the template's compose file and
  image volume would then persist nothing.
- **Change homelab-k8s in lockstep** (`TRACKIE_STATE_DIR=/config/state`): one line, but an image bump
  without it would move the state to the container's disk without a word.

## Consequences

- Clients: none. `/snapshot` and `/health` are byte-identical for the same poller state.
- Operators with a `config.yml`: move it to `/etc/trackie/config.yaml` and flatten its keys (wiki,
  Deployment, "Upgrading"); trackie refuses to start until they do. Env-only deployments: nothing.
- `TRACKIE_MAX_BACKOFF` users: rename it (refused at start).
- Python 3.13 or later; uv; the stricter template ruff set and strict mypy over tests too.
- Wiki: In-Depth-Configuration, HTTP-API-Reference, Deployment, Troubleshooting (`error_kind: config`).
- Rollback: the previous image digest; the state files are unchanged in format.

## Open questions

None.
