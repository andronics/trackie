This page follows one polling cycle from "time to fetch" to the JSON you get from `/snapshot`. For the code-level module map, see [Architecture Internals](Architecture-Internals).

### The Big Picture

```text
 IPTorrents ──┐                        ┌── Sonarr / Radarr / Readarr / Lidarr (grab history)
              │  Peers + Hit & Run     │── Prowlarr (grab history)
 TorrentDay ──┤  pages, every ~45 min  │── qBittorrent (torrent list)
              ▼                        ▼
           ┌──────────────────────────────────┐
           │ trackie                          │
           │  fetch → parse → records         │
           │                    │             │
           │                    ▼             │
           │  matching: tracker ID → hash ────┼──► state/mappings.json
           │                    │             │
           │                    ▼             │
           │  GET /snapshot   GET /health     │──► state/<tracker>.json
           └──────────────────────────────────┘
                        ▲
                        │ one call per run
                    qbt-rules (or curl, a script, a dashboard…)
```

### 1. Fetch

For each enabled tracker, trackie loads two pages, **Hit & Run first**:

| Page | IPTorrents | TorrentDay |
|------|------------|------------|
| Hit & Run | `/seeding_required.php` | `/seed_back.php` |
| Peers | `/peers?u=<your user ID>` | `/peers?u=<your user ID>` |

Hit & Run goes first because it needs no user ID, and its page header links to your profile, so trackie reads your user ID from there instead of making you configure it. Requests to the same site are at least 5 seconds apart (plus a little randomness), with a normal browser User-Agent. See [Supported Trackers](Supported-Trackers) for what each page shows.

### 2. Parse

Each page has its own parser. They find table columns by their **header text**, not their position, so a reordered or added column doesn't shift values into the wrong field. Sizes become bytes and durations become seconds; the raw text is kept alongside for debugging.

A parser that can't find what it expects raises an error rather than returning nothing. A login page, an error page or a redesign must never look like "you have no torrents". See [Polling and Failures](Polling-and-Failures).

The page header gives the **account** stats too: ratio, total uploaded and downloaded, bonus points, and how many torrents the site thinks you're seeding.

### 3. Build Records

Peers rows and Hit & Run rows are joined on the tracker's torrent ID into one **record** per torrent, with a status:

| Status | Meaning |
|--------|---------|
| `hnr` | On the Hit & Run list. Stays there until reset or 1:1, even if you've started seeding again |
| `required` | On Peers with time still to go ("4.9 days to go"), or still downloading |
| `satisfied` | On Peers, seeding requirement met (plain "2.1 weeks", no "to go") |

`hnr` wins over the others. A torrent that's on **neither** page doesn't get a record at all: the tracker doesn't see it seeding, so its status is unknown. Unknown is never treated as satisfied.

### 4. Match

Each record is matched to a qBittorrent info hash, in order of confidence: *arr grab history, then Prowlarr's release title, then the name (plus size for shortened names). Every mapping is saved the moment it's found. Full details in [Matching](Matching).

### 5. Serve

- **`GET /snapshot`** puts matched records under `torrents`, keyed by hash, and the rest in `unmatched`, alongside each tracker's account stats and when it was last fetched.
- **`GET /health`** reports, per tracker, whether the last fetch worked, whether the cookie still works, and when the next fetch is due, plus the state of matching.

Both are built from the **last good** data. If the latest fetch failed, you get the previous data with its original `fetched_at`, and decide for yourself whether it's too old. See [HTTP API Reference](HTTP-API-Reference) and [Snapshot Fields](Snapshot-Fields).

### 6. Persist

Each tracker's last good data is written to `state/<tracker>.json`, and all mappings to `state/mappings.json`, atomically (write then rename). After a restart the saved data is served straight away, while a fresh fetch of every tracker runs in the background.
