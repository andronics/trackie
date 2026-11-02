Every field in a `/snapshot` response, what it means, and where it comes from. For the response as a whole, see [HTTP API Reference](HTTP-API-Reference#get-snapshot).

Units are always in the field name: `_b` is bytes, `_s` is seconds. Timestamps are ISO 8601 in UTC with a `Z` suffix.

### Torrent Records

One per tracker torrent ID, found under `torrents.<hash>` when matched, or in `unmatched` when not.

| Field | Type | Meaning |
|-------|------|---------|
| `tracker` | `"ipt"` \| `"td"` | Which tracker this record is from |
| `tracker_id` | int | The tracker's own torrent ID (`/t/<id>`, `details.php?id=<id>`) |
| `name` | string | Torrent name as the tracker shows it. From the Hit & Run page when available, since that's always the full name |
| `name_truncated` | bool | `true` when `name` is a shortened Peers name ending in `...` |
| `status` | `"hnr"` \| `"required"` \| `"satisfied"` | See [How It Works](How-It-Works#3-build-records). `hnr` beats `required` beats `satisfied` |
| `remaining_s` | int \| null | Seeding time still owed ("4.9 days to go"). `null` once the requirement is met, or when not on the Peers page |
| `seed_time_s` | int \| null | Time seeded, shown only once the requirement is met ("2.1 weeks"). `null` while time is still owed |
| `uploaded_b` | int | Lifetime upload on the tracker for this torrent. From Peers when present (live), else from Hit & Run |
| `downloaded_b` | int | Lifetime download on the tracker, same sources |
| `ratio` | float \| null | `uploaded_b / downloaded_b`, 3 decimals. `null` when nothing was downloaded (e.g. a cross-seed) |
| `gap_b` | int \| null | Hit & Run only: bytes still needed to reach 1:1 |
| `hnr_seed_time_s` | int \| null | Hit & Run only: time seeded so far toward the H&R reset (336 h IPT, 72 h TD) |
| `on_peers` | bool | The tracker currently sees this torrent seeding or leeching |
| `on_hnr` | bool | The torrent is on the Hit & Run list |
| `seen_at` | timestamp | When the page this record came from was fetched |
| `hash` | string \| null | qBittorrent info hash, lowercase. `null` in `unmatched` |
| `match` | `"exact"` \| `"fuzzy"` \| null | How confident the hash is. See [Matching](Matching) |
| `match_source` | string \| null | What made the match: `sonarr`, `radarr`, `readarr`, `lidarr`, `prowlarr`, `name` or `name+size` |

**Reading `remaining_s` and `seed_time_s` together:**

| On Peers? | `remaining_s` | `seed_time_s` | Means |
|-----------|---------------|---------------|-------|
| yes | number | `null` | Still owes this much time |
| yes | `null` | number | Requirement met; seeded this long |
| no | `null` | `null` | Not seen on Peers (only on Hit & Run) |

**Precision:** the sites show one decimal place of the largest unit, so `seed_time_s` for "2.1 weeks" is only accurate to about ±8 hours, and `remaining_s` for "1.6 days" to about ±2.5 hours.

### Account Records

One per tracker, under `accounts.<tracker>`.

| Field | Type | Meaning | Source |
|-------|------|---------|--------|
| `ratio` | float \| null | Your overall ratio on the site | Page header (cached by the site, ~10 min) |
| `uploaded_b`, `downloaded_b` | int | Account totals | Page header |
| `bonus` | float \| null | Bonus points | Page header |
| `seeding`, `leeching` | int | Active torrents as the site counts them | Page header (cached; can lag the rows) |
| `hnr_count` | int | Torrents on the Hit & Run list right now | Counted from the live rows, **not** the banner |
| `hnr_limit` | int | H&Rs allowed before a warning (default 40) | [Config](In-Depth-Configuration#trackers) |
| `hnr_grace_s` | int | How long a torrent can be unseeded before it counts (default 432000 IPT, 259200 TD) | Config |
| `min_ratio` | float | The site's minimum account ratio (default 1.0 IPT, 0.3 TD) | Config |
| `announce_hosts` | list | Hostnames that identify this tracker in qBittorrent's tracker URLs | Learned from matches + config |
| `seen_at` | timestamp | When the header was read | Fetch |

Useful comparisons: `ratio < min_ratio` means the account is below the site minimum; `hnr_count` approaching `hnr_limit` means a warning is close.

### Top Level

| Field | Type | Meaning |
|-------|------|---------|
| `generated_at` | timestamp | When this response was built |
| `fetched_at` | object | `{tracker: timestamp}`: when each tracker's data was last fetched **successfully**. The age of the data |
| `accounts` | object | `{tracker: account record}` |
| `torrents` | object | `{hash: torrent record}` for matched records |
| `unmatched` | list | Torrent records with no hash yet |

A tracker that has never been fetched successfully is simply absent from `fetched_at` and `accounts`.
