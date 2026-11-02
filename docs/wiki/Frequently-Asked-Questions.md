# Frequently Asked Questions

**[General](#general-questions)**

- [Why not just use qBittorrent's seeding time?](#q-why-not-just-use-qbittorrents-seeding-time)
- [Does trackie change anything?](#q-does-trackie-change-anything-on-the-trackers-or-in-qbittorrent)
- [Which trackers are supported?](#q-which-trackers-are-supported)
- [Can I use only one tracker?](#q-can-i-use-only-one-tracker)
- [Will this get my account in trouble?](#q-will-this-get-my-account-in-trouble)
- [What changed in 0.2?](#q-what-changed-in-02)

**[Setup](#setup-questions)**

- [Why can't it use Prowlarr's cookie?](#q-prowlarr-already-has-my-cookie-why-do-i-have-to-copy-it-again)
- [How long does a cookie last?](#q-how-long-does-a-cookie-last)
- [Do I need Sonarr/Radarr?](#q-do-i-need-sonarr-radarr-or-prowlarr)
- [Do I need to find my user ID?](#q-do-i-need-to-find-my-user-id)
- [Do I need to configure announce hosts?](#q-do-i-need-to-configure-announce-hosts)

**[Data](#data-questions)**

- [How fresh is the data?](#q-how-fresh-is-the-data)
- [Why is a torrent missing?](#q-a-torrent-im-seeding-isnt-in-the-snapshot-why)
- [Why don't the banner numbers match?](#q-why-doesnt-hnr_count-match-the-sites-banner)
- [How accurate are the times?](#q-how-accurate-are-remaining_s-and-seed_time_s)
- [What's the difference between exact and fuzzy?](#q-whats-the-difference-between-exact-and-fuzzy)
- [What happens if I delete a series in Sonarr?](#q-what-happens-to-matching-if-i-delete-a-series-in-sonarr)

---

## General Questions

### Q: Why not just use qBittorrent's seeding time?

Because the tracker decides, not the client. qBittorrent's seeding time can reset when a torrent is moved or re-added, counts time the tracker never saw (a stalled announce, an unreachable tracker), and knows nothing about Hit & Runs. TorrentDay's own rules say: *"Use the Peer page, not your client… (The site is always right!)"*

### Q: Does trackie change anything on the trackers or in qBittorrent?

No. It only reads: two pages per tracker, grab history from the *arr apps and Prowlarr, and the torrent list from qBittorrent. It never zaps an H&R, posts a form, or touches a torrent.

### Q: Which trackers are supported?

IPTorrents and TorrentDay. See [Supported Trackers](Supported-Trackers), and [Adding a Tracker](Adding-a-Tracker) if you want to write parsers for another.

### Q: Can I use only one tracker?

Yes. Set `TRACKIE_TD_ENABLED=false` (or `TRACKIE_IPT_ENABLED=false`) and leave out that cookie.

### Q: Will this get my account in trouble?

trackie is designed to look like you checking your own stats now and then: two page loads per site every 45-55 minutes, with backoff on errors and a browser User-Agent. Neither site's rules forbid it at the time of writing, but you're responsible for checking your trackers' current rules. See [Security](Security#site-etiquette).

### Q: What changed in 0.2?

Inside, a lot: trackie moved to FastAPI on uvicorn and to the shared project templates. Outside, little: `/snapshot` and `/health` are byte-for-byte the same, the image name, port and variables are the same, and a tracker without a cookie no longer stops startup. A config *file* needs its keys moved. See [Deployment](Deployment#upgrading).

## Setup Questions

### Q: Prowlarr already has my cookie. Why do I have to copy it again?

Prowlarr's API returns private fields like the cookie as `********`, so there's no supported way to read it back. Reading Prowlarr's database directly would break whenever Prowlarr changes its schema. Copy the cookie from your browser instead; when it expires, update both.

### Q: How long does a cookie last?

Usually months, until you log out or change your password. When it stops working, `/health` shows `"cookie_ok": false` and `"error_kind": "auth"`. trackie keeps serving the last good data in the meantime.

### Q: Do I need Sonarr, Radarr or Prowlarr?

No, but without them matching falls back to names only, which is weaker and can't handle shortened names without size information. With Sonarr and Radarr, expect nearly every torrent to match exactly. Without any sources, every record lands in `unmatched`.

### Q: Do I need to find my user ID?

No. trackie reads it from the profile link on the Hit & Run page. You can still set `TRACKIE_IPT_USER_ID` if you prefer.

### Q: Do I need to configure announce hosts?

Usually not. trackie learns them from exact matches. Configure `announce_hosts` only if you have no *arr history for it to learn from. See [Matching](Matching#how-announce-hosts-are-learned).

## Data Questions

### Q: How fresh is the data?

Each tracker is fetched every 45-55 minutes; check `fetched_at` for the exact time. The page header stats are cached by the sites themselves for about 10 minutes on top of that.

### Q: A torrent I'm seeding isn't in the snapshot. Why?

Either the tracker doesn't see it (it's not on your Peers page: check the torrent's tracker status in qBittorrent), or it's there but in `unmatched` instead of `torrents` because no hash was found. Search `unmatched` for its name. See [Troubleshooting](Troubleshooting#a-torrent-is-missing).

### Q: Why doesn't `hnr_count` match the site's banner?

The banner is a cached aggregate refreshed every ten minutes or so; `hnr_count` is counted from the live rows on the Hit & Run page. The rows are right.

### Q: How accurate are `remaining_s` and `seed_time_s`?

As accurate as the site shows them: one decimal place of the largest unit. "2.1 weeks" is ±8 hours; "17.0 hours" is ±3 minutes. Good for "is this done?", too coarse for "is it within the next hour?" on long timers.

### Q: What's the difference between `exact` and `fuzzy`?

`exact` comes from a record that ties the tracker ID to the hash or to the full release name: *arr history or Prowlarr. `fuzzy` is a name (and size) comparison. Act on `fuzzy` with care, especially for anything destructive. See [Matching](Matching).

### Q: What happens to matching if I delete a series in Sonarr?

Nothing, if trackie had already seen it: mappings are saved the first time they're found and never re-derived. That's why `state/mappings.json` must live on a volume.
