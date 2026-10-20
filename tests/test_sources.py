import pytest
import requests
import requests_mock

from trackie.sources import PAGE_SIZE, ArrClient, ProwlarrClient, QbtClient, SourceError

KEY = "0123456789abcdef0123456789abcdef"
HASH = "A" * 40


def arr_record(i: int, date: str, download_id: str = HASH) -> dict[str, object]:
    return {
        "date": date,
        "downloadId": download_id,
        "sourceTitle": f"Show S01E{i:02d}",
        "data": {"guid": f"https://iptorrents.com/t/{1000 + i}"},
    }


def test_arr_grabs_page_until_short_page(requests_mock: requests_mock.Mocker) -> None:
    full = [arr_record(1, "2026-10-20T10:00:00Z")] * PAGE_SIZE
    last = [arr_record(2, "2026-10-01T10:00:00Z")]
    m = requests_mock.get(
        "http://sonarr:8989/api/v3/history",
        [{"json": {"records": full}}, {"json": {"records": last}}],
    )
    grabs = ArrClient("sonarr", "http://sonarr:8989/", KEY, "v3").grabs()
    assert len(grabs) == PAGE_SIZE + 1
    assert grabs[0].hash == "a" * 40
    assert grabs[0].url == "https://iptorrents.com/t/1001"
    assert m.call_count == 2
    first = m.request_history[0]
    assert first.headers["X-Api-Key"] == KEY
    assert KEY not in first.url
    assert first.qs["eventtype"] == ["1"]
    assert first.qs["sortdirection"] == ["descending"]


def test_arr_grabs_stop_at_checkpoint(requests_mock: requests_mock.Mocker) -> None:
    records = [
        arr_record(1, "2026-10-20T10:00:00Z"),
        arr_record(2, "2026-10-10T10:00:00Z"),
        arr_record(3, "2026-10-01T10:00:00Z"),
    ]
    requests_mock.get("http://radarr:7878/api/v3/history", json={"records": records})
    grabs = ArrClient("radarr", "http://radarr:7878", KEY, "v3").grabs(since="2026-10-05T00:00:00Z")
    assert [g.title for g in grabs] == ["Show S01E01", "Show S01E02"]


def test_arr_skips_non_qbittorrent_downloads(requests_mock: requests_mock.Mocker) -> None:
    records = [
        arr_record(1, "2026-10-20T10:00:00Z", "SABnzbd_nzo_abc"),
        arr_record(2, "2026-10-20"),
    ]
    requests_mock.get("http://lidarr:8686/api/v1/history", json={"records": records})
    grabs = ArrClient("lidarr", "http://lidarr:8686", KEY, "v1").grabs()
    assert [g.title for g in grabs] == ["Show S01E02"]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"status_code": 401}, "API key"),
        ({"status_code": 500}, "HTTP 500"),
        ({"text": "<html>"}, "JSON"),
        ({"exc": requests.ConnectionError(f"failed with key {KEY}")}, "ConnectionError"),
    ],
)
def test_arr_errors_never_leak_the_key(
    requests_mock: requests_mock.Mocker, kwargs: dict[str, object], match: str
) -> None:
    requests_mock.get("http://sonarr:8989/api/v3/history", **kwargs)
    with pytest.raises(SourceError, match=match) as info:
        ArrClient("sonarr", "http://sonarr:8989", KEY, "v3").grabs()
    assert KEY not in str(info.value)


def test_prowlarr_grabs(requests_mock: requests_mock.Mocker) -> None:
    records = [
        {
            "date": "2026-10-20T10:00:00Z",
            "successful": True,
            "data": {
                "url": "https://iptorrents.com/download.php/7766504/Show.S01E01.torrent",
                "grabTitle": "Show.S01E01.1080p.WEB.H264-GRP",
            },
        },
        {"date": "2026-10-20T09:00:00Z", "successful": False, "data": {"grabTitle": "failed"}},
        {"date": "2026-10-20T08:00:00Z", "successful": True, "data": {"url": "x"}},
    ]
    requests_mock.get("http://prowlarr:9696/api/v1/history", json={"records": records})
    grabs = ProwlarrClient("http://prowlarr:9696", KEY).grabs()
    assert len(grabs) == 1
    assert grabs[0].title == "Show.S01E01.1080p.WEB.H264-GRP"
    assert grabs[0].hash is None


def test_qbt_torrents_without_login(requests_mock: requests_mock.Mocker) -> None:
    requests_mock.get(
        "http://qbt:8080/api/v2/torrents/info",
        json=[
            {
                "hash": "ABC" + "0" * 37,
                "name": "Show S01E01",
                "total_size": 1000,
                "tracker": "https://routing.bgp.technology:443/x/announce?passkey=secret",
            },
            {"hash": "d" * 40, "name": "Idle", "size": 5, "tracker": ""},
        ],
    )
    torrents = QbtClient("http://qbt:8080").torrents()
    assert torrents[0].hash == "abc" + "0" * 37
    assert torrents[0].host == "routing.bgp.technology"
    assert torrents[0].size == 1000
    assert torrents[1].host is None
    assert not any("passkey" in str(t) for t in torrents)


def test_qbt_login(requests_mock: requests_mock.Mocker) -> None:
    login = requests_mock.post("http://qbt:8080/api/v2/auth/login", text="Ok.")
    requests_mock.get("http://qbt:8080/api/v2/torrents/info", json=[])
    client = QbtClient("http://qbt:8080", "admin", "pw")
    client.torrents()
    client.torrents()
    assert login.call_count == 1


def test_qbt_login_refused(requests_mock: requests_mock.Mocker) -> None:
    requests_mock.post("http://qbt:8080/api/v2/auth/login", text="Fails.")
    with pytest.raises(SourceError, match="login refused"):
        QbtClient("http://qbt:8080", "admin", "wrong").torrents()
