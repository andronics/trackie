# trackie

**Ask the tracker, not the client.** trackie reads your seeding obligations straight from private tracker websites (IPTorrents and TorrentDay), works out which qBittorrent torrent each one belongs to, and serves the lot as one JSON document. qBittorrent knows how long *it* has seeded; only the tracker knows whether *the tracker* agrees.

```json
{
  "torrents": {
    "3f2a…c91e": {
      "tracker": "td",
      "tracker_id": 10329334,
      "status": "required",
      "remaining_s": 82800,
      "ratio": 0.031,
      "match": "exact",
      "match_source": "sonarr"
    }
  }
}
```

That's a real record shape: torrent `3f2a…c91e` still owes TorrentDay 23 hours of seeding, and trackie knows that hash belongs to tracker ID 10329334 because Sonarr's grab history says so. A few things it's for:

- ⏳ **See what's still owed:** every torrent's "time to go" exactly as the site counts it
- 🚨 **Catch Hit & Runs early:** torrents on the H&R list, with the bytes still needed to clear them
- 📉 **Watch account standing:** ratio against the site minimum, H&R count against the warning limit
- 🔗 **Know which torrent is which:** tracker IDs mapped to qBittorrent hashes, kept forever
- 🤖 **Feed automation:** a single `/snapshot` call that [qbt-rules](https://github.com/andronics/qbt-rules) (or anything else) can act on

One Docker container, two cookies, and the trackers do the rest. **[Get started →](Quick-Start)**

## Table of Contents

- [Introduction](Introduction)
- [Quick Start](Quick-Start)
- [How It Works](How-It-Works)
- [Supported Trackers](Supported-Trackers)
- [Matching](Matching)
- [Snapshot Fields](Snapshot-Fields)
- [HTTP API Reference](HTTP-API-Reference)
- [CLI Reference](CLI-Reference)
- [Polling and Failures](Polling-and-Failures)
- [Security](Security)
- [In-Depth Configuration](In-Depth-Configuration)
- [Deployment](Deployment)
- [Using with qbt-rules](Using-with-qbt-rules)
- [Frequently Asked Questions](Frequently-Asked-Questions)
- [Troubleshooting](Troubleshooting)
- **For Developers**
  - [Contributing](Contributing)
  - [Architecture Internals](Architecture-Internals)
  - [Adding a Tracker](Adding-a-Tracker)
  - [Testing Guide](Testing-Guide)
  - [Release Process](Release-Process)
- [License](License)
