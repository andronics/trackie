# Testing Guide

trackie has a pytest suite covering every module, run on each supported Python version (3.13 and up) in CI. This page maps what's there and how fixtures work, since they're the one part that needs care.

## Running the tests

```sh
uv sync                                                   # once: the venv, with the dev tools
uv run pytest                                             # unit tests, with an 80% coverage floor
uv run pytest tests/unit/test_parsers.py --no-cov         # a subset, no coverage floor
RUN_INTEGRATION=1 uv run pytest -m integration --no-cov   # integration tests (none yet)
```

CI runs these too, and every one blocks a merge:

```sh
sh scripts/checks.sh                           # template checks, the wiki standard, version and lock, tracker user IDs
uv run ruff check && uv run ruff format --check
uv run mypy                                    # strict, over src/, tests/ and scripts/
uv run scripts/gen-wiki.py --check             # generated wiki tables are current
python3 scripts/check-personal-data.py         # public IPs (and the denylist, when set)
```

## Test layout

```text
tests/
├── conftest.py          # clean_env (no TRACKIE_* leakage, no /config of this machine's), write_config, page
├── fixtures/
│   ├── ipt_peers.html   # scrubbed real pages, saved 2026-10-20
│   ├── ipt_hnr.html
│   ├── td_peers.html
│   ├── td_hnr.html
│   └── raw/             # git-ignored: unscrubbed originals
├── integration/         # real external systems, marked @pytest.mark.integration; skipped unless RUN_INTEGRATION=1
└── unit/
    ├── helpers.py       # tracker_cfg(), app_config(), T0: shared builders
    ├── test_units.py    # sizes, durations, numbers
    ├── test_parsers.py  # all four parsers against the real pages, plus failure modes
    ├── test_fetch.py    # SiteClient against requests-mock: auth, Cloudflare, gaps, no secret leaks
    ├── test_config.py   # keys and variables, defaults, the 0.2 renames, legacy paths, secrets
    ├── test_snapshot.py # record status rules, account fields, torrents/unmatched split
    ├── test_store.py    # atomic state files
    ├── test_poller.py   # schedule, backoff, zero-row guard, last-good, restart, missing cookie, matching hookup
    ├── test_sources.py  # *arr/Prowlarr/qBittorrent clients: paging, checkpoints, errors
    ├── test_matching.py # every step of the matching chain, host learning, persistence
    ├── test_api.py      # the endpoints, the lifespan, the byte format and the qbt-rules contract
    ├── test_cli.py      # trackie version, config and serve
    └── test_version.py
```

### Fixtures

The parser tests run against **real pages saved from the sites**, because hand-written HTML would only test what the author already understood. Real pages carry personal data, so there's a strict workflow:

1. **Save** the page from a logged-in browser into `tests/fixtures/raw/` (git-ignored).
2. **Scrub** it:

   ```bash
   scripts/scrub-fixture.py tests/fixtures/raw/td_peers.html tests/fixtures/td_peers.html
   ```

   This reads the user ID and username from the page's own profile link and replaces them, and every public IPv4 address, with placeholders: `1000000`, `fixtureuser`, `192.0.2.x` (a documentation range). Nothing personal is hard-coded in the script.
3. **Check** it:

   ```bash
   scripts/check-personal-data.py tests/fixtures/td_peers.html
   scripts/check-tracker-user-ids.py tests/fixtures/td_peers.html
   ```

4. **Look** at the diff yourself before committing. The scripts catch IDs and IPs, not everything.

Over every tracked file, CI fails on:

- a public IPv4 address (private, loopback and documentation ranges are fine; `Chrome/130.0.0.0`-style version numbers are ignored): `scripts/check-personal-data.py`, the template's guard,
- a tracker user-ID parameter (`u=<digits>`) other than the placeholder: `scripts/check-tracker-user-ids.py`, run by `sh scripts/checks.sh`,
- any string in the denylist repository secret (your real username, IDs and IP, one per line): `PERSONAL_DATA_DENYLIST`, or trackie's original `FIXTURE_DENYLIST` through the *Fixture denylist* workflow.

A line containing `personal-data: ok` is exempt from the IP and user-ID checks, for deliberate test values such as `u=77`; the denylist still applies.

**The check scans tracked files only**, so run it after `git add`, not before.

## Writing tests

- **Parser changes** belong in `test_parsers.py`, checked against the real fixtures: exact counts, a few hand-verified values, and the failure that the change guards against.
- **Anything that handles a secret** gets a test that the secret doesn't appear in the exception or `repr`. See `test_network_error_never_leaks_the_cookie`.
- **Poller and matcher tests** use fakes (`FakeClient`, `FakeHistory`, `FakeQbt`) and an injectable clock, never real time or network.
- Use `tests/unit/helpers.py` builders rather than constructing config objects by hand.
- **API changes** keep `test_api.py`'s contract test green: it checks every field qbt-rules reads, and validates the documents against `schemas.py` in strict mode.
- Every behaviour change needs a test that fails without it; don't lower the coverage floor or skip a test to make CI pass.
