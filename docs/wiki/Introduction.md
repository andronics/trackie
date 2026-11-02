
## What it is

trackie is a small **read-only companion service** for private tracker users. Every 45 minutes or so it signs in to each tracker's website with your session cookie, reads two pages (your **Peers** page and your **Hit & Run** page), and turns them into one JSON snapshot: what's still owed, what's satisfied, what's a Hit & Run, and how your account stands against the site's rules.

It then works out which qBittorrent torrent each tracker entry belongs to, using your Sonarr/Radarr/Readarr/Lidarr grab history, Prowlarr's history, and qBittorrent's own torrent list, so every record can be looked up by **info hash**.

```bash
curl -s http://trackie:8080/snapshot | jq '.torrents | to_entries[] | select(.value.status == "hnr") | .value.name'
```

See [Quick Start](Quick-Start) to get this running.

## How it works

One process, two parts. A background poller fetches each tracker's Hit & Run and Peers pages on a slow, jittered timer, joins their rows into one record per torrent, saves the last good result, and then asks the *arr apps, Prowlarr and qBittorrent which info hash each tracker torrent is. An HTTP API (FastAPI, run by `trackie serve`) serves what the poller last got right: `/snapshot` for consumers such as qbt-rules, `/health` for people. A failed fetch keeps the previous data and its age. The details are in [How It Works](How-It-Works), [Matching](Matching) and [Polling and Failures](Polling-and-Failures).

### Why use it?

**qBittorrent's numbers aren't the tracker's numbers:**

- qBittorrent's seeding time resets or drifts when a torrent is moved, rechecked, or re-added; the tracker's count doesn't
- The tracker counts seeding only while it can *see* you announce: a stalled or erroring torrent may look "seeding" locally and not at all on the site
- Ratio on the tracker includes every client and every session; qBittorrent only knows its own
- TorrentDay's own rules say it plainly: *"Use the Peer page, not your client… (The site is always right!)"*

**Acting on the wrong numbers is expensive:**

- Delete a torrent one hour early and it lands on the Hit & Run list
- More than 40 unseeded H&Rs at once earns an account warning; three warnings and the account is jailed or demoted
- Keeping everything forever "just in case" fills disks and wastes slots

trackie gives automation (and you) the tracker's view, so cleanup can wait until the site agrees.

### Key features

✅ **The site's own numbers** - Seeding time remaining, H&R gap and account ratio straight from the tracker's pages

✅ **Hash matching** - Tracker torrent IDs mapped to qBittorrent info hashes via *arr history, Prowlarr, then name and size

✅ **Mappings kept forever** - *arr history disappears when a series is deleted and Prowlarr forgets after ~4 weeks; trackie saves every mapping the first time it sees it

✅ **Learns your trackers** - Works out which announce hostnames belong to which tracker from the exact matches, no configuration needed

✅ **Account standing** - Ratio vs. the site minimum, live H&R count vs. the warning limit

✅ **Fails safe** - A failed or suspicious fetch never replaces good data; missing data is "unknown", never "satisfied"

✅ **Polite by design** - Two page loads per tracker per cycle, at least 5 s apart, every 45-55 minutes, backing off on errors

✅ **Secrets stay secret** - Cookies and API keys via Docker secrets (`_FILE` variables); never logged, never in error messages

✅ **Personal data stays out of git** - CI fails the build if a committed file contains a public IP or tracker user ID

✅ **Docker-first deployment** - One container, GHCR images (`linux/amd64`), healthcheck built in

## When not to use it

- **Not an automation engine.** It never touches qBittorrent; it only reads. Acting on the data is [qbt-rules](Using-with-qbt-rules)'s job (or yours).
- **Not a login bot.** It never handles your password. You give it a browser session cookie; when that expires, `/health` tells you.
- **Not real-time.** The tracker pages are read every 45-55 minutes, and the values on them are coarse ("2.1 weeks" is ±8 hours). Fine for "is this satisfied?", not for minute-precise thresholds.

### Requirements

- **Docker** and Docker Compose, or Kubernetes (see [Deployment](Deployment))
- An account on **IPTorrents** and/or **TorrentDay**, and its session cookie
- **qBittorrent** with the Web UI enabled (for hash matching)
- Optional but recommended: **Sonarr / Radarr / Readarr / Lidarr** and **Prowlarr**, for exact matching
