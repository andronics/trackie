This page covers when trackie fetches, what happens when a fetch goes wrong, and why it never throws away good data.

### Schedule

Each tracker is polled on its own timer:

| Setting | Default | Meaning |
|---------|---------|---------|
| `poll.interval` | 2700 s (45 min) | Time between successful fetches. **Minimum 600 s**; anything lower is refused at startup |
| `poll.jitter` | 600 s (10 min) | Up to this much is added at random each time, so fetches don't land on the same minute |
| `poll.max_backoff` | 21600 s (6 h) | The longest wait after repeated failures |
| `<site>.request_gap` (`ipt`, `td`) | 5 s | Minimum time between the page loads of one fetch (plus up to half again at random): H&R, then each Peers page |

Every tracker is fetched once at startup; any saved data is served until that fetch completes. Each poll is two page loads per tracker. Nothing else triggers a fetch; a busy consumer calling `/snapshot` costs the trackers nothing.

### Backoff

After a failure the wait doubles: 1.5 h, 3 h, then 6 h and staying there, each plus jitter. One success resets it. One tracker failing never delays the other.

### Kinds of Failure

| `error_kind` | What happened | Typical cause | Data served |
|--------------|---------------|---------------|-------------|
| `auth` | The site returned a login page (redirect to a `login` URL, or a password field on the page) | Cookie expired or was invalidated by logging out | Last good |
| `fetch` | No usable response: network error, timeout, HTTP 4xx/5xx, or a **Cloudflare** challenge page | Site down, DNS, rate limiting | Last good |
| `parse` | A page arrived but didn't look as expected: missing table, missing column, unknown time unit | The site changed its layout | Last good |
| `suspect` | The page parsed, but the result is implausible (see below) | An error page that happens to parse, a half-loaded page | Last good |
| `error` | Anything else | A bug in trackie: check `docker logs` | Last good |

**In every case the previous data stays**, with its original `fetched_at`. The snapshot never goes empty because the site had a bad minute.

### The Zero-Row Guard

A Peers page with no rows at all is far more often a broken page than a genuinely empty account. trackie rejects it as `suspect` when either:

- the page header says you're seeding at least one torrent, or
- the last good fetch had **5 or more** Peers rows.

A first-ever fetch with no rows and a header saying 0 seeding is accepted: that really is an empty account.

### Why "Unknown" Is Never "Satisfied"

Three things can make a torrent disappear from the data, and none of them mean the obligation is met:

1. **It dropped off the Peers page** because the tracker no longer sees it: paused, stalled, erroring, or the client is offline. No record means *unknown*.
2. **A fetch failed** and the snapshot is old. `fetched_at` tells you how old.
3. **It isn't matched** to a hash. It sits in `unmatched`, and nothing keyed by hash will find it.

A consumer that deletes torrents should only act on `status: satisfied`, on recent data, with an `exact` match. That's the contract [qbt-rules integration](Using-with-qbt-rules) is designed around.

### Restart Behaviour

On start, trackie loads `state/<tracker>.json` and serves it immediately, with its original `fetched_at`, then fetches every tracker. `cookie_ok` is `null` until that first attempt finishes. Frequent restarts therefore mean frequent fetches; avoid restart loops. Mappings, learned hosts and history checkpoints come back from `state/mappings.json`, so matching picks up where it left off.
