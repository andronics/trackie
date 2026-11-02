> **Available in qbt-rules [v0.8.0](https://github.com/andronics/qbt-rules/releases/tag/v0.8.0) and later.** qbt-rules' own field reference is on its [Available Fields](https://github.com/andronics/qbt-rules/wiki/Available-Fields#tracker-seeding-stats-trackie) page.

trackie exists so that [qbt-rules](https://github.com/andronics/qbt-rules) can make cleanup decisions on the tracker's numbers instead of qBittorrent's. Every tracker-specific detail stays in trackie: qbt-rules gains one generic field namespace, `tracker.*`, and knows nothing about either site.

### How It Plugs In

- **One fetch per run, only when needed.** The first `tracker.*` lookup in a job fetches `/snapshot`; every other torrent and rule in that job reuses it. A job whose rules never mention `tracker.*` makes no request to trackie at all.
- **Looked up by hash.** A torrent's `tracker.*` fields come from `torrents.<its hash>` in the snapshot.
- **Fails safe.** If trackie is unreachable, the tracker's data is older than `max_age`, or the torrent has no record, the lookup raises a `DataNotReadyError` and the rule is **skipped** for that torrent on that run. It doesn't evaluate as false, so a `none:` group can't match by accident either. A rule can never delete a torrent because trackie was down. Unreachable trackie is logged once per job, not once per torrent.

Configuration in qbt-rules' `config.yml`:

```yaml
integrations:
  trackie:
    url: http://trackie:8080       # QBT_RULES_INTEGRATIONS_TRACKIE_URL
    max_age: 3 hours               # older tracker data counts as none; seconds or a duration
    timeout: 10                    # seconds for the /snapshot request
```

Using a `tracker.*` field without `url` set, or an unknown `tracker.*` field, is a `FieldError`, the same as a typo in any other field.

### Torrent Fields

From the torrent's own record. See [Snapshot Fields](Snapshot-Fields) for exact meanings.

| Field | From | Notes |
|-------|------|-------|
| `tracker.status` | `status` | `required`, `satisfied` or `hnr` |
| `tracker.remaining` | `remaining_s` | Seconds still owed; `null` once met, so numeric comparisons don't match |
| `tracker.seed_time` | `seed_time_s` | Seconds seeded, once the requirement is met |
| `tracker.uploaded`, `tracker.downloaded` | `uploaded_b`, `downloaded_b` | Bytes, as the tracker counts them |
| `tracker.ratio` | `ratio` | |
| `tracker.gap` | `gap_b` | H&R only: bytes still needed for 1:1 |
| `tracker.hnr_seed_time` | `hnr_seed_time_s` | H&R only: seconds toward the reset |
| `tracker.on_peers`, `tracker.on_hnr` | `on_peers`, `on_hnr` | |
| `tracker.name`, `tracker.id` | `name`, `tracker_id` | |
| `tracker.tracker` | `tracker` | `ipt` or `td` |
| `tracker.match`, `tracker.match_source` | `match`, `match_source` | `exact`/`fuzzy`; `sonarr`, `prowlarr`, `name+size`… |
| `tracker.age` | computed | Seconds since the record's page was fetched |

### Account Fields

For whichever tracker the torrent is on. That's found from the torrent's record when it has one, otherwise from its tracker URLs against each account's `announce_hosts`, so account checks work even for torrents trackie hasn't matched, such as manual adds.

| Field | From |
|-------|------|
| `tracker.account.ratio`, `.min_ratio` | `ratio`, `min_ratio` |
| `tracker.account.ratio_ok` | computed: `ratio >= min_ratio` |
| `tracker.account.hnr_count`, `.hnr_limit`, `.hnr_grace` | `hnr_count`, `hnr_limit`, `hnr_grace_s` |
| `tracker.account.uploaded`, `.downloaded`, `.bonus` | account totals |
| `tracker.account.seeding`, `.leeching` | the site's active counts |
| `tracker.account.age` | computed: seconds since the header was read |

Fields also work in notify templates (`"${tracker.status} on ${tracker.tracker}"`); a missing value renders as empty rather than failing the message.

### Example Rules

Remove torrents only when the tracker agrees, and only on an exact match:

```yaml
- id: remove-tracker-satisfied
  meta:
    description: "Delete torrents the tracker says are fully seeded"
  context: nightly-cleanup
  conditions:
    all:
      - field: tracker.status
        operator: ==
        value: satisfied
      - field: tracker.match
        operator: ==
        value: exact
  actions:
    - type: delete_torrent
      params:
        delete_files: true
```

Rescue a Hit & Run that's still in the client:

```yaml
- id: rescue-hit-and-run
  meta:
    description: "Force-seed anything the tracker lists as a Hit & Run"
  conditions:
    all:
      - field: tracker.status
        operator: ==
        value: hnr
  actions:
    - type: force_start
    - type: add_tag
      params:
        tags: [hnr-rescue]
```

Hold back deletes while an account is under the site minimum. Place it **before** the delete rule, with `stop_on_match`:

```yaml
- id: hold-while-account-ratio-low
  meta:
    description: "Keep uploading torrents while account ratio is below the site minimum"
  stop_on_match: true
  conditions:
    all:
      - field: tracker.status
        operator: ==
        value: satisfied
      - field: tracker.account.ratio_ok
        operator: ==
        value: false
      - field: info.upspeed
        operator: ">"
        value: 0
  actions:
    - type: add_tag
      params:
        tags: [ratio-builder]
```

Durations are seconds: compare them with numeric operators (`tracker.remaining <= 3600`). qbt-rules' `older_than`/`newer_than` operators take timestamps, not durations.

### Without qbt-rules

trackie's data is just as usable by hand or from a script. See [HTTP API Reference](HTTP-API-Reference#quick-checks) for ready-made `jq` queries.
