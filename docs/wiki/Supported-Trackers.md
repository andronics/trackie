trackie currently supports **IPTorrents** (`ipt`) and **TorrentDay** (`td`). Both run a similar site codebase and show the same two things: a Peers page that counts down open seeding obligations, and a Hit & Run page that lists broken ones. Adding another site means writing two parsers; see [Adding a Tracker](Adding-a-Tracker).

### Site Rules

As stated on each site's Hit & Run page and rules (October 2026). These are only **defaults** in trackie: every value can be overridden in config if a site changes its rules. See [In-Depth Configuration](In-Depth-Configuration#trackers).

| | IPTorrents | TorrentDay |
|---|---|---|
| H&R clears after | 336 h (14 days) seeded, or 1:1 | 72 h seeded, or 1:1 |
| Warning when | more than 40 torrents unseeded for 120 h | more than 40 torrents unseeded for 72 h |
| Warning lasts | 2 months | 2 months |
| After 3 warnings | jailed | demoted to Leecher |
| Minimum account ratio | 1.0 | 0.3 |
| trackie key | `ipt` | `td` |
| `hnr_limit` / `hnr_grace` / `min_ratio` defaults | 40 / 432000 s / 1.0 | 40 / 259200 s / 0.3 |

Both sites count Freeleech downloads toward the 1:1 ratio.

### The Peers Page

Every torrent the tracker currently sees you on, split into Seeders and Leechers.

| Column | Example | What trackie does with it |
|--------|---------|---------------------------|
| Torrent | `A Remarkable Place To Die S02E05 1080p TVNZ WEB...` | `name`; long names are cut short with `...`, so `name_truncated: true` |
| Uploaded / Downloaded | `0 B (197 MB)` | This session's transfer, then **lifetime** in brackets; trackie uses the lifetime figure. An empty cell means nothing yet |
| Seeding Time | `4.9 days to go` / `2.1 weeks` | "to go" means the requirement is still open (`remaining_s`); no "to go" means it's met (`seed_time_s`) |
| Client, IP | | Ignored, and never copied into trackie's data |

IPT redesigned its Peers page around 2026-10-31, and trackie reads both layouts. The new one differs:

- A **Status** column (`Seeding`, `Leeching`) replaces the Seeders and Leechers sections.
- **Uploaded / Downloaded** show this session's transfer (`-` for none) with a `Total 5.95 GB` line under it for the lifetime. With no `Total` line the two are the same. A line such as `494 B/s` is the current rate, and trackie ignores it.
- **Seeding** shows `569 h` with `Requirement met` under it, or `247 h to go`.
- Names are shown in full, so `name_truncated` is `false`. There is no progress column, so `progress_pct` is `null`.
- Rows come 100 to a page (`Page 1 of 3`), and trackie fetches every page, with the request gap before each one.
- The IP is now under **Address**, which is also never copied.

**Absence means unknown.** A paused, stalled or erroring torrent drops off the Peers page. trackie never reads that as "satisfied".

**Values are coarse.** "2.1 weeks" has one decimal place, so it's only accurate to about ±8 hours. Fine for a yes/no, fuzzy near a threshold.

### The Hit & Run Page

Failures only: torrents you stopped seeding before reaching the requirement.

| Column | IPTorrents | TorrentDay |
|--------|------------|------------|
| Torrent | Full name, link `/t/<id>` | Full name, link `details.php?id=<id>` |
| Uploaded / Downloaded | Lifetime totals | Lifetime totals |
| Gap | Bytes still needed for 1:1 → `gap_b` | Same |
| Seeding Time | Seeded so far toward the reset ("0.0 hours") → `hnr_seed_time_s` | Same ("0.0 h") |
| Extra | "N hours ago" stopped, zap cost in points | Clear cost in bonus points or upload credit |

### The Page Header

Both sites show your account stats at the top of every page. trackie reads ratio, uploaded, downloaded, bonus points and the active seeding/leeching counts.

**These are cached by the site**, refreshed roughly every 10 minutes, while the table rows are live. They can disagree: a banner might say "116 torrents require seeding" while the rows show 70. trackie counts H&Rs from the **rows** (`hnr_count`) and treats header numbers as approximate.

### Announce Hosts

qBittorrent shows which tracker a torrent uses by its announce URL's hostname, and private trackers often announce on unrelated-looking domains (several per site). trackie **learns** which hostnames belong to which tracker from its exact matches, so you rarely need to list them. See [Matching](Matching#how-announce-hosts-are-learned).

### Site Policy

Neither site's rules forbid scripted access to your own pages. trackie keeps its footprint to roughly what a person checking their own stats would do: two page loads per site per cycle, every 45-55 minutes, never triggered by anything else, backing off on errors. Read your trackers' current rules yourself before running it; they're the authority, not this page.
