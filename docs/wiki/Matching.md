The trackers never show a torrent's **info hash**, and the torrent comment field is empty on both sites, so there's no direct way to tell which qBittorrent torrent a tracker row is about. trackie works it out from the apps that grabbed the torrent in the first place.

### The Matching Chain

Tried in order, for each tracker torrent ID that doesn't already have a mapping:

| Step | Source | Match | How |
|------|--------|-------|-----|
| 1 | Sonarr, Radarr, Readarr, Lidarr | `exact` | Each grab records `downloadId` (the qBittorrent hash) and `data.guid` (the tracker URL, which contains the torrent ID). One look-up, no guessing |
| 2 | Prowlarr | `exact` | Each grab records the tracker URL and the full release title, but no hash. The title is compared with qBittorrent torrent names on that tracker; exactly one must match |
| 3 | Name | `fuzzy` | A full name (Hit & Run names are always full) must equal exactly one qBittorrent torrent name on that tracker |
| 4 | Name + size | `fuzzy` | A shortened Peers name (20+ characters before the `...`) must be the start of exactly one torrent name, **and** the tracker-side download must be 98–115% of that torrent's size |

Names are compared case-insensitively, with dots, underscores and spaces treated alike (`Show.Name_S01E01` = `show name s01e01`).

Anything still unmatched goes in the snapshot's `unmatched` list: visible, but never attached to a torrent.

### Why History Has to Be Saved

Both history sources forget:

- **\*arr history** is deleted along with a series or movie. Delete a show you've finished and every grab record for it goes too, while its torrents may still be seeding.
- **Prowlarr** only keeps about four weeks.

So trackie **saves every mapping the first time it finds it**, in `mappings.json` in `state_dir`, and never re-derives it. It also saves Prowlarr's release titles, so step 2 still works for a torrent grabbed months ago. Keep `state_dir` on a volume.

History is read **incrementally**: trackie remembers the newest grab date it has seen from each app and, on later passes, stops paging once it reaches it. The first pass reads everything (about 15 pages for a large Sonarr), later ones usually a single page.

### Which Mapping Wins

- An `exact` mapping is **never replaced**. If two apps disagree about a torrent ID, the first one stays and a warning is logged.
- A `fuzzy` mapping is **upgraded** the moment an `exact` one turns up.
- One qBittorrent torrent can only be claimed once per tracker. A name candidate that's already mapped to another torrent ID is skipped.

### How Announce Hosts Are Learned

Name matching (steps 2-4) only considers qBittorrent torrents on the **right tracker**, which qBittorrent identifies by announce hostname. trackie learns these from step 1: every exact match ties a hash to a tracker, and qBittorrent says which host that hash announces to. Each exact match is a vote.

A host is assigned to a tracker when **at least 3 votes** agree and they make up **at least 90%** of that host's votes. Not 100%, because a torrent uploaded unchanged to both sites has the *same* hash on each, so the occasional vote for the other tracker is normal.

Learned hosts are merged with any you configure in `announce_hosts` and shown in each account's `announce_hosts` in the snapshot. You only need to configure them if you have no *arr history to learn from.

### When Matching Runs

After every tracker fetch, so new rows get hashes straight away. A failing source (Sonarr down, qBittorrent login refused) is reported in `/health` under `matching.errors`; the other sources still run, and existing mappings are unaffected.

### What Good Looks Like

On a library grabbed mostly through Sonarr and Radarr, expect almost everything to match exactly at step 1. One real setup: 427 of 427 tracker torrents matched, 424 through *arr history and 3 through Prowlarr titles (episodes whose series had been deleted from Sonarr), none needing fuzzy matching.

A lot of `unmatched` records usually means torrents added by hand, or by an app trackie isn't configured to read. See [Troubleshooting](Troubleshooting#lots-of-unmatched-records).
