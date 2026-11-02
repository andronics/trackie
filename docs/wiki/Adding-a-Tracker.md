trackie's tracker support is two parsers and one `Site` entry. Everything downstream (records, matching, the API) is tracker-neutral. This page walks through adding a third site; the existing `ipt.py` and `td.py` are the best reference, since one uses bare `<table class=t1>` markup and the other semantic `tdm-*` classes.

### 1. Check the Site Has What You Need

You need two pages that a logged-in user can see:

- A **Peers**-style page listing your active torrents with, per row: a link containing the torrent ID, lifetime uploaded and downloaded, and seeding time with some marker for "still owed".
- A **Hit & Run** page listing failures with the gap still owed.

And a page header showing your ratio, totals and active counts. If the site only offers some of this, the corresponding fields will need to be optional; raise it in an issue first.

### 2. Save and Scrub Fixtures

Save both pages from a logged-in browser (**File → Save Page As**, HTML only) into `tests/fixtures/raw/` (git-ignored), then scrub them:

```bash
scripts/scrub-fixture.py tests/fixtures/raw/xyz_peers.html tests/fixtures/xyz_peers.html
scripts/scrub-fixture.py tests/fixtures/raw/xyz_hnr.html   tests/fixtures/xyz_hnr.html
scripts/check-personal-data.py tests/fixtures/xyz_*.html
```

Open the scrubbed copies and search for anything else personal (email, invite links, passkeys in RSS or download links) before committing. See [Testing Guide](Testing-Guide#fixtures).

### 3. Write the Parsers

Create `src/trackie/parsers/xyz.py` with three functions:

```python
def parse_account(doc: BeautifulSoup) -> AccountStats: ...
def parse_peers(html: str) -> PeersPage: ...
def parse_hnr(html: str) -> HnrPage: ...
```

Use the helpers in `parsers/common.py` rather than re-implementing them:

| Helper | Use for |
|--------|---------|
| `soup(html)` | Always: it uses lxml, which closes unclosed `<tr>`/`<td>` the way a browser does |
| `header_index(row)` + `require_columns(...)` + `cell(...)` | Finding columns by header text, never by position |
| `session_lifetime(text, what)` | "0 B (35.7 MB)" cells |
| `seed_time(text, what)` | Peers seed-time cells → `(seed_time_s, remaining_s)` |
| `size()`, `duration()` | Anything else; they raise `ParseError` with context |
| `PRIVATE_COLUMNS` | Columns never copied into `raw` (user, IP) |

Rules every parser must follow:

- **Raise `ParseError`, never return empty, when the page isn't what you expect**: no account header (likely a login page), no table, missing columns, a row without a torrent link.
- **An empty H&R list is valid only when the page confirms it**: IPT checks for its explanatory text, TD for its "H&R Torrents: 0" counter. Find the equivalent on the new site.
- **Prefer full names**: if the site puts the full name in a `title` attribute while the text is cut short, use the attribute.
- Never copy username, user ID or IP into any returned field.

### 4. Register the Site

Add an entry to `SITES` in `sites.py`:

```python
"xyz": Site(
    key="xyz",
    name="XyzTracker",
    base_url="https://xyz.example",
    peers_path="/peers?u={uid}",
    hnr_path="/hnr.php",
    parse_peers=xyz.parse_peers,
    parse_hnr=xyz.parse_hnr,
    hnr_limit=40,
    hnr_grace_s=72 * 3600,
    min_ratio=0.5,
    id_in_url=re.compile(r"//(?:[\w-]+\.)*xyz\.example/(?:details\.php\?id=|download\.php/)(\d+)", re.I),
),
```

`id_in_url` must match the torrent ID in **every** URL form the *arr apps and Prowlarr record for this site (details pages, download links, and every mirror domain), or matching will miss grabs. Check real `data.guid` values in Sonarr's history and `data.url` in Prowlarr's.

The H&R page must contain a `/u/<id>` profile link for user ID discovery. If the site's profile URLs look different, `fetch.py`'s `_PROFILE_LINK` needs generalising.

Config picks the site up automatically: `TRACKIE_XYZ_COOKIE_FILE`, `xyz.*` and so on (`config.py` builds each site's settings from `SITES`).

### 5. Test

Mirror `tests/unit/test_parsers.py`'s IPT and TD sections: exact row counts from your fixtures, a few rows' values checked against the page by eye, account stats, the empty-H&R case, and the failure cases (login page, missing table, missing column). See [Testing Guide](Testing-Guide).

Finally, run it once against the live site with a real cookie and compare `/snapshot` with the pages in your browser.
