"""Real fixed MusicBox request construction over a synthetic requests boundary."""

import asyncio
import importlib.util
import json
import sys

import pytest

from hub.errors import HubError
from modules.accounts.netease import NeteaseCredential
from modules.catalog.netease import NeteaseProtocol
from modules.catalog.netease_worker import execute

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("NEMbox") is None,
    reason="optional fixed MusicBox SDK not installed",
)


@pytest.fixture
def sdk(tmp_path, monkeypatch):
    for key in (
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
    ):
        directory = tmp_path / key
        directory.mkdir()
        monkeypatch.setenv(key, str(directory))
    import NEMbox.api as upstream
    import requests

    assert NeteaseProtocol.available()
    captured, sent = [], []
    encrypt = upstream.encrypted_request

    def encryption(params):
        captured.append(json.loads(json.dumps(params)))
        return encrypt(params)

    monkeypatch.setattr(upstream, "encrypted_request", encryption)
    ids = [{"id": 1}, None, {"id": 1}] + [{"id": n} for n in range(4, 206)]

    class Rig:
        code = 200
        status = 200
        more = True
        malformed = False
        account_uid = 10001
        count = 205
        tracks = ids

        def payload(self, request):
            if "nuser/account/get" in request.url:
                return {
                    "code": 200,
                    "account": {"id": self.account_uid},
                    "profile": {"userId": self.account_uid, "nickname": "synthetic"},
                }
            if "playlist/detail" in request.url:
                return {
                    "code": self.code,
                    "playlist": {
                        "id": 77,
                        "name": "list",
                        "trackCount": self.count,
                        "trackIds": self.tracks,
                    },
                }
            if "song/detail" in request.url:
                wanted = json.loads(captured[-1]["ids"])
                return {
                    "code": self.code,
                    "songs": [
                        {"id": n, "name": f"song-{n}", "dt": 240000, "ar": [], "al": {}}
                        for n in reversed(wanted)
                        if n != 14
                    ],
                }
            if "recommend/songs" in request.url:
                return {"code": self.code, "data": {"dailySongs": [{"id": 7}] * 35}}
            if "recommend/resource" in request.url:
                return {"code": self.code, "recommend": [{"id": 77}]}
            return {
                "code": self.code,
                "playlist": [{"id": 77}],
                "playlists": [{"id": 77}],
                "more": self.more,
            }

    rig = Rig()

    def send(session, request, **kwargs):
        sent.append(request)
        assert not session.trust_env
        assert not request.headers.get("X-Real-IP") and not request.headers.get(
            "X-Forwarded-For"
        )
        assert kwargs["allow_redirects"] is False
        response = requests.Response()
        response.status_code = rig.status
        response._content = (
            b"<html>synthetic sensitive error</html>"
            if rig.malformed
            else json.dumps(rig.payload(request)).encode()
        )
        response._content_consumed = True
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    return rig, captured, sent


def payload(operation, page=1, private=False):
    return {
        "operation": operation,
        "page": page,
        "cookies": {"MUSIC_U": "synthetic-a", "__csrf": "csrf"} if private else {},
        "uid": "10001" if private else None,
        "playlist_id": "77",
    }


def test_sdk_public_offset_no_cookie_no_disk_http_cache(sdk):
    rig, captured, sent = sdk
    data = execute(payload("public_playlists", page=2))
    assert data["has_more"] and data["items"] == [{"id": 77}]
    assert captured[-1]["offset"] == 30 and captured[-1]["limit"] == 30
    assert len(sent) == 1 and "MUSIC_U" not in sent[0].headers.get("Cookie", "")
    assert "params=" in sent[0].body and "encSecKey=" in sent[0].body


@pytest.mark.parametrize(
    "operation", ["user_playlists", "recommend_playlists", "recommend_songs"]
)
def test_sdk_private_verifies_uid_both_sides_uses_source_endpoint(sdk, operation):
    rig, captured, sent = sdk
    result = execute(payload(operation, private=True))
    assert result["items"]
    assert len(sent) == 3
    assert all("MUSIC_U=synthetic-a" in r.headers.get("Cookie", "") for r in sent)
    assert "nuser/account/get" in sent[0].url and "nuser/account/get" in sent[-1].url
    if operation == "user_playlists":
        assert captured[1]["uid"] == 10001
    if operation == "recommend_songs":
        assert len(result["items"]) == 30 and result["has_more"]
        assert "/weapi/v3/discovery/recommend/songs" in sent[1].url


@pytest.mark.parametrize(
    "page,count,more", [(1, 100, True), (2, 100, True), (3, 5, False)]
)
def test_sdk_full_ids_reconstruct_order_duplicates_unknown_and_missing_details(
    sdk, page, count, more
):
    rig, captured, sent = sdk
    result = execute(payload("playlist_page", page=page))
    assert len(result["items"]) == count and result["has_more"] == more
    assert result["source_total"] == 205
    wanted = rig.tracks[(page - 1) * 100 : page * 100]
    assert [r["id"] if r else None for r in result["items"]] == [
        r["id"] if r and r["id"] != 14 else None for r in wanted
    ]
    assert len(json.loads(captured[-1]["ids"])) == len(
        set(json.loads(captured[-1]["ids"]))
    )
    assert not any("player/url" in r.url for r in sent)


@pytest.mark.parametrize(
    "code,expected",
    [
        (301, "platform_auth_required"),
        (405, "rate_limited"),
        (500, "upstream_contract"),
    ],
)
def test_sdk_business_errors_do_not_become_empty_success(sdk, code, expected):
    rig, captured, sent = sdk
    rig.code = code
    with pytest.raises(HubError) as error:
        execute(payload("public_playlists"))
    assert error.value.code == expected


@pytest.mark.parametrize(
    "status,expected",
    [
        (302, "upstream_contract"),
        (401, "platform_auth_required"),
        (429, "rate_limited"),
        (503, "platform_unavailable"),
    ],
)
def test_sdk_http_status_and_redirects_are_explicit(sdk, status, expected):
    rig, captured, sent = sdk
    rig.status = status
    with pytest.raises(HubError) as error:
        execute(payload("public_playlists"))
    assert error.value.code == expected


def test_sdk_identity_switch_truncated_playlist_and_missing_continuation(sdk):
    rig, captured, sent = sdk
    rig.account_uid = 20002
    with pytest.raises(HubError) as error:
        execute(payload("user_playlists", private=True))
    assert error.value.code == "binding_changed" and len(sent) == 1
    rig.count = 206
    with pytest.raises(HubError) as error:
        execute(payload("playlist_page"))
    assert error.value.code == "incomplete"
    rig.more = None
    with pytest.raises(HubError) as error:
        execute(payload("public_playlists"))
    assert error.value.code == "upstream_contract"


def test_short_lived_worker_executes_without_importing_nembox_in_hub(monkeypatch):
    # The invalid operation performs no network I/O, but starts the real isolated worker.
    before = set(sys.modules)

    async def run():
        with pytest.raises(HubError) as error:
            await NeteaseProtocol().read(NeteaseCredential("{}"), "unsupported")
        assert error.value.code == "upstream_contract"

    asyncio.run(run())
    assert not {n for n in set(sys.modules) - before if n.startswith("NEMbox")}


def test_sdk_transport_timeout_is_transient_not_empty_success(sdk, monkeypatch):
    import requests

    def timeout(*args, **kwargs):
        raise requests.ReadTimeout("synthetic upstream diagnostics")

    monkeypatch.setattr(requests.Session, "send", timeout)
    with pytest.raises(HubError) as error:
        execute(payload("public_playlists"))
    assert error.value.code == "platform_unavailable"
