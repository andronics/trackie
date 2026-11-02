# Deployment

trackie is one container, `ghcr.io/andronics/trackie` (`linux/amd64`), that runs `trackie serve`: uvicorn with the FastAPI app, listening on port 8080. It runs as uid 1000, needs outbound HTTPS to the trackers and HTTP to qBittorrent and the *arr apps, and keeps its state in `state_dir`. Manifests live in [contrib/](https://github.com/andronics/trackie/tree/main/contrib), versioned with the code; release-please moves their image tag to each new release.

**Image tags:** `:edge`, `:main` and `:main-<sha>` from every push to `main`; `:<branch>` and `:<branch>-<sha>` from `dev/**` and `feat/**` branches (deleted after 7 days); `:X.Y.Z`, `:X.Y` and `:latest` for each release, plus `:X` from 1.0. See [Release Process](Release-Process).

## Docker Compose

The template's hardened compose file mounts `./config` at `/etc/trackie` (read-only) and `./state` at `/var/lib/trackie`:

```sh
mkdir -p config state secrets
cp contrib/trackie.example.yaml config/config.yaml   # edit it, or delete it and use variables only
docker compose -f contrib/docker/compose.yml up -d
docker compose -f contrib/docker/compose.yml logs -f
```

Give the cookies and API keys as files: uncomment the `./secrets:/run/secrets/trackie:ro` volume and set, for example, `TRACKIE_IPT_COOKIE_FILE: /run/secrets/trackie/ipt_cookie` and `TRACKIE_SONARR_API_KEY_FILE: /run/secrets/trackie/sonarr_api_key` in `environment:`. The files must be readable by uid 1000. The [Quick Start](Quick-Start) shows the same with Compose `secrets:`.

The compose file binds the port to `127.0.0.1` only. trackie has no authentication: put it on the Docker network its consumers (qBittorrent, qbt-rules) are on, and drop `ports:` if nothing on the host needs it. See [Security](Security#network-exposure).

The image's `HEALTHCHECK` polls `/health`, which answers 200 while the process is up; `/readyz` answers 503 if the poller has stopped.

### Kubernetes

The homelab deployment (homelab-k8s, `apps/pvr/wave4/trackie.yaml`) runs one replica with the `Recreate` strategy (one poller, and a ReadWriteOnce volume), uid/gid 1000, the tracker cookies and *arr API keys from a SOPS Secret mounted at `/run/secrets` and named by `TRACKIE_*_FILE` variables, and a Service `trackie:8080` that qbt-rules reads (`QBT_RULES_INTEGRATIONS_TRACKIE_URL=http://trackie:8080`).

Its PersistentVolumeClaim is mounted at `/config`, the image's volume before 0.2, with the data in `/config/state`. trackie uses `/config/state` whenever `state_dir` isn't set and that directory exists, so the deployment needs no change. A readiness probe can use `httpGet: {path: /readyz, port: http}`; a TCP probe on the port also works.

## Upgrading

Read the [CHANGELOG](https://github.com/andronics/trackie/blob/main/CHANGELOG.md) entries between your version and the new one; breaking changes are marked ⚠. Then:

- Compose: change the image tag, then `docker compose up -d`.
- Kubernetes: change the image (tag or digest) in the Deployment.

**From 0.1 to 0.2:**

- **Environment-only deployments need nothing.** The image name, port, `/snapshot` and `/health` (byte for byte) and every variable but one are unchanged, and an existing `/config/state` is still used.
- **`TRACKIE_MAX_BACKOFF` is now `TRACKIE_POLL_MAX_BACKOFF`.** The old name stops startup with that message.
- **A config file moves and its keys change:** `/config/config.yml` becomes `/etc/trackie/config.yaml` (or `TRACKIE_CONFIG`), `trackers.<site>.*` becomes `<site>.*`, `sources.<app>.*` becomes `<app>.*`, and `http.timeout` becomes `timeout`. An old file, or old keys, stop startup with what to change. See [In-Depth Configuration](In-Depth-Configuration#changes-in-02).
- **A tracker with no cookie** no longer stops startup: it is reported as `error_kind: config` in `/health` and never fetched.
- **New endpoints:** `/readyz`, `/version`, and the OpenAPI schema at `/openapi.json`.

**Rolling back:** run the previous image. 0.1 reads the same state files, from `/config/state` only: a deployment that mounts `/config` (like the homelab one) rolls back as it is.
