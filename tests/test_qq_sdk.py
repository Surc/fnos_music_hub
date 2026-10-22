"""Pinned real SDK request/sign/error paths with a synthetic transport; no platform calls."""

import asyncio
import copy

import httpx
import pytest

from hub.errors import HubError
from modules.accounts.hot_qq import CredentialSnapshot
from modules.catalog.qq import QqProtocol

sdk = pytest.importorskip("qqmusic_api")


@pytest.fixture
def wire(monkeypatch):
    from qqmusic_api.utils.android_session import AndroidSessionManager
    from qqmusic_api.utils.qimei import QimeiManager

    async def session(self):
        return None

    async def qimei(self):
        return {"q16": "synthetic", "q36": "synthetic"}

    monkeypatch.setattr(AndroidSessionManager, "ensure", session)
    monkeypatch.setattr(QimeiManager, "get_cached", qimei)

    class Wire:
        def __init__(self):
            self.allowed = {"10001": "synthetic-key"}
            self.calls, self.closed, self.code, self.error, self.data = (
                [],
                0,
                0,
                None,
                {},
            )

        async def request(self, request):
            assert request.url in {
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                "https://u.y.qq.com/cgi-bin/musics.fcg",
            }
            self.calls.append(request)
            if self.error:
                raise self.error
            payload = request.kwargs["json"]
            assert payload["comm"]["authst"] == self.allowed[payload["comm"]["qq"]]
            method = payload["req_0"]["method"]
            return httpx.Response(
                200,
                request=httpx.Request("POST", request.url),
                json={
                    "code": 0,
                    "req_0": {
                        "code": self.code,
                        "data": {}
                        if method == "GetLoginUserInfo"
                        else copy.deepcopy(self.data),
                    },
                },
            )

        async def close(self):
            self.closed += 1

    boundary = Wire()
    original = sdk.Client
    monkeypatch.setattr(
        sdk, "Client", lambda **kwargs: original(**kwargs, transport=boundary)
    )
    snapshot = CredentialSnapshot(
        "10001",
        (("musicid", 10001), ("str_musicid", "10001"), ("musickey", "synthetic-key")),
    )
    return boundary, snapshot


@pytest.mark.parametrize(
    "operation,method,params",
    [
        ("verify", "GetLoginUserInfo", {}),
        ("recommend_playlists", "GetRecommendFeed", {"From": 20, "Size": 20}),
        (
            "recommend_songs",
            "get_radio_track",
            {"id": 99, "num": 5, "from": 0, "scene": 0, "song_ids": []},
        ),
        ("created_playlists", "GetPlaylistByUin", {"uin": "10001"}),
        (
            "playlist_page",
            "CgiGetDiss",
            {
                "disstid": 77,
                "dirid": 9,
                "tag": 1,
                "song_begin": 100,
                "song_num": 100,
                "userinfo": 1,
                "orderlist": 1,
                "onlysonglist": 0,
            },
        ),
    ],
)
def test_pinned_sdk_builds_private_read_requests_without_refresh(
    wire, operation, method, params
):
    boundary, snapshot = wire
    boundary.data = {"tracks": [None, {"id": 1}, {"id": 1}]}
    result = asyncio.run(
        QqProtocol().read(snapshot, operation, page=2, cursor=20, playlist_id="77", dirid="9")
    )
    last = boundary.calls[-1].kwargs["json"]["req_0"]
    assert last["method"] == method and last["param"] == params
    assert all(r.kwargs["json"]["req_0"]["method"] != "Login" for r in boundary.calls)
    assert boundary.closed == 1
    if operation != "verify":
        assert result == boundary.data  # Raw entries survive SDK model parsing.


@pytest.mark.parametrize("code", [1000, 104400, 104401])
def test_real_sdk_expired_credentials_fail_without_anonymous_retry(wire, code):
    boundary, snapshot = wire
    boundary.code = code
    with pytest.raises(HubError) as error:
        asyncio.run(QqProtocol().read(snapshot, "recommend_playlists"))
    assert error.value.code == "platform_auth_required"
    assert len(boundary.calls) == 1
    assert boundary.closed == 1


def test_real_sdk_network_failure_is_sanitized_and_does_not_refresh(wire):
    from qqmusic_api.core.transport import TransportTimeout

    boundary, snapshot = wire
    boundary.error = TransportTimeout("synthetic-key must never reach the response")
    with pytest.raises(HubError) as error:
        asyncio.run(QqProtocol().read(snapshot, "recommend_playlists"))
    assert error.value.code == "platform_unavailable"
    assert "synthetic-key" not in error.value.message
    assert len(boundary.calls) == 1 and boundary.closed == 1


def test_real_sdk_concurrent_clients_keep_separate_frozen_credentials(wire):
    boundary, a = wire
    boundary.allowed["20002"] = "second-user-key"
    b = CredentialSnapshot(
        "20002",
        (("musicid", 20002), ("str_musicid", "20002"), ("musickey", "second-user-key")),
    )
    changed = a.credential()
    changed["musickey"] = "cannot-change-original"

    async def both():
        await asyncio.gather(
            QqProtocol().read(a, "created_playlists"),
            QqProtocol().read(b, "created_playlists"),
        )

    asyncio.run(both())
    assert len(boundary.calls) == 4 and boundary.closed == 2
    assert {r.kwargs["json"]["comm"]["qq"] for r in boundary.calls} == {
        "10001",
        "20002",
    }
    assert a.credential()["musickey"] == "synthetic-key"
