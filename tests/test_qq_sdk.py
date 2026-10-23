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
                        else self.data(payload["req_0"]["param"])
                        if callable(self.data)
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
        QqProtocol().read(
            snapshot, operation, page=2, cursor=20, playlist_id="77", dirid="9"
        )
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


def test_real_sdk_two_full_scans_use_offset_pages_and_keep_duplicate_unknown_entries(
    wire, tmp_path
):
    from hub.domain import Principal
    from hub.store import Store
    from modules.catalog.qq import QqCatalog
    from modules.catalog.qq_snapshot import QqSnapshots

    boundary, credentials = wire
    rows = [
        {"id": i + 1, "mid": f"mid{i + 1}", "title": f"song-{i + 1}"}
        for i in range(205)
    ]
    rows[100], rows[101] = rows[99], None

    def response(params):
        start = params["song_begin"]
        selected = rows[start : start + params["song_num"]]
        return {
            "dirinfo": {"id": 77, "dirid": 9},
            "songlist": selected,
            "songlist_size": len(selected),
            "total_song_num": len(rows),
            "hasmore": int(start + len(selected) < len(rows)),
        }

    boundary.data = response
    grant = {
        "account_ref": "synthetic",
        "binding_generation": 1,
        "credential_revision": 1,
        "uin": "10001",
    }

    class Accounts:
        async def snapshot(self, owner):
            return grant, credentials

        async def validate(self, owner, given, snapshot):
            assert given == grant and snapshot == credentials

    store = Store(tmp_path / "data")
    captures = QqSnapshots(QqCatalog(Accounts(), QqProtocol(), store))
    owner = Principal(instance_id="synthetic-nas", user_guid="synthetic-user")

    async def authenticated():
        pass

    async def execute():
        capture = await captures.begin(
            owner, {"provider": "qq", "id": "77", "dirid": "9"}, "synthetic"
        )
        return await captures.run(owner, capture["id"], lambda: None, authenticated)

    capture = asyncio.run(execute())
    assert capture["complete"]
    entries = store.manifest(owner, capture["manifest_id"])["ordered_entries"]
    assert len(entries) == 205
    assert entries[99]["song"]["track"] == entries[100]["song"]["track"]
    assert entries[101]["song"]["track"] is None
    reads = [
        c.kwargs["json"]["req_0"]
        for c in boundary.calls
        if c.kwargs["json"]["req_0"]["method"] == "CgiGetDiss"
    ]
    assert [r["param"]["song_begin"] for r in reads] == [0, 100, 200, 0, 100, 200]
    assert boundary.closed == 6
