from collections.abc import Callable

import pytest
import requests
import requests_mock

from trackie.fetch import AuthError, FetchError, SiteClient
from trackie.sites import SITES

from .helpers import tracker_cfg

COOKIE = tracker_cfg("ipt").cookie
Page = Callable[[str], str]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def client(key: str, clock: FakeClock | None = None, **overrides: object) -> SiteClient:
    clock = clock or FakeClock()
    return SiteClient(SITES[key], tracker_cfg(key, **overrides), clock=clock, sleep=clock.sleep)


@pytest.mark.parametrize("key", ["ipt", "td"])
def test_fetch_discovers_user_id_and_parses_both_pages(
    key: str, page: Page, requests_mock: requests_mock.Mocker
) -> None:
    site = SITES[key]
    requests_mock.get(f"{site.base_url}{site.hnr_path}", text=page(f"{key}_hnr"))
    peers = requests_mock.get(f"{site.base_url}/peers?u=1000000", text=page(f"{key}_peers"))

    result = client(key).fetch()

    assert result.user_id == 1000000
    assert peers.called_once
    assert len(result.peers.rows) == {"ipt": 129, "td": 172}[key]
    assert len(result.hnr.rows) == {"ipt": 9, "td": 2}[key]
    sent = requests_mock.request_history[0].headers
    assert sent["Cookie"] == COOKIE
    assert sent["User-Agent"] == "test-agent"


def test_configured_user_id_is_used(page: Page, requests_mock: requests_mock.Mocker) -> None:
    site = SITES["ipt"]
    requests_mock.get(f"{site.base_url}{site.hnr_path}", text=page("ipt_hnr"))
    peers_url = f"{site.base_url}/peers?u=77"  # personal-data: ok
    peers = requests_mock.get(peers_url, text=page("ipt_peers"))
    assert client("ipt", user_id=77).fetch().user_id == 77
    assert peers.called_once


def test_requests_are_spaced_out(page: Page, requests_mock: requests_mock.Mocker) -> None:
    site = SITES["td"]
    requests_mock.get(f"{site.base_url}{site.hnr_path}", text=page("td_hnr"))
    requests_mock.get(f"{site.base_url}/peers?u=1000000", text=page("td_peers"))
    clock = FakeClock()
    client("td", clock).fetch()
    assert len(clock.slept) == 1
    assert 5 <= clock.slept[0] <= 7.5


def test_login_redirect_is_an_auth_error(requests_mock: requests_mock.Mocker) -> None:
    site = SITES["ipt"]
    requests_mock.get(
        f"{site.base_url}{site.hnr_path}",
        status_code=302,
        headers={"Location": f"{site.base_url}/login.php?returnto=%2Fseeding_required.php"},
    )
    requests_mock.get(f"{site.base_url}/login.php", text="<form><input name=username></form>")
    with pytest.raises(AuthError):
        client("ipt").fetch()


def test_login_form_in_place_is_an_auth_error(requests_mock: requests_mock.Mocker) -> None:
    site = SITES["td"]
    requests_mock.get(
        f"{site.base_url}{site.hnr_path}",
        text='<form method=post><input name="username"><input type="password" name="password"></form>',
    )
    with pytest.raises(AuthError):
        client("td").fetch()


def test_cloudflare_challenge_is_a_fetch_error(requests_mock: requests_mock.Mocker) -> None:
    site = SITES["td"]
    requests_mock.get(
        f"{site.base_url}{site.hnr_path}",
        status_code=403,
        text="<title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/x.js'>",
    )
    with pytest.raises(FetchError, match="Cloudflare"):
        client("td").fetch()


def test_server_error_is_a_fetch_error(requests_mock: requests_mock.Mocker) -> None:
    site = SITES["ipt"]
    requests_mock.get(f"{site.base_url}{site.hnr_path}", status_code=502, text="bad gateway")
    with pytest.raises(FetchError, match="HTTP 502"):
        client("ipt").fetch()


def test_network_error_never_leaks_the_cookie(requests_mock: requests_mock.Mocker) -> None:
    site = SITES["ipt"]
    requests_mock.get(f"{site.base_url}{site.hnr_path}", exc=requests.ConnectionError(COOKIE))
    with pytest.raises(FetchError) as info:
        client("ipt").fetch()
    assert "SECRETVALUE" not in str(info.value)
    assert info.value.__cause__ is None


def test_messages_never_contain_the_user_id(
    page: Page, requests_mock: requests_mock.Mocker
) -> None:
    site = SITES["td"]
    requests_mock.get(f"{site.base_url}{site.hnr_path}", text=page("td_hnr"))
    requests_mock.get(f"{site.base_url}/peers?u=1000000", status_code=503)
    with pytest.raises(FetchError) as info:
        client("td").fetch()
    assert "1000000" not in str(info.value)
    assert "/peers?u=…" in str(info.value)
