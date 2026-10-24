"""Synthetic account/catalog boundaries. No real Cookie, NAS or platform acceptance."""

import asyncio
import copy
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from test_core import ORIGIN, Upstream

from hub.app import create_app
from hub.config import Settings
from hub.domain import Principal
from hub.errors import HubError
from modules.accounts.netease import parse_cookie

COOKIE = "MUSIC_U=synthetic-a; __csrf=synthetic-csrf"


def raw_song(id=1):
    return {
        "id": id,
        "name": f"song-{id}",
        "dt": 240000,
        "ar": [{"name": "synthetic artist"}],
        "al": {"name": "album"},
    }


class Protocol:
    def __init__(self):
        self.calls, self.error, self.gate = [], None, None
        self.entered, self.release = threading.Event(), threading.Event()
        self.results = {
            "public_playlists": {
                "items": [{"id": 77, "name": "public list"}, None],
                "has_more": True,
            },
            "user_playlists": {
                "items": [{"id": 78, "name": "private list"}],
                "has_more": False,
            },
            "recommend_playlists": {
                "items": [{"id": 79, "name": "account recommendation"}],
                "has_more": False,
            },
            "recommend_songs": {
                "items": [raw_song(), None, raw_song()],
                "has_more": False,
            },
            "playlist_page": {
                "items": [raw_song(), None, raw_song()],
                "has_more": False,
                "source_total": 103,
                "playlist": {"id": 77, "name": "list"},
            },
        }

    async def read(self, snapshot, operation, **kwargs):
        self.calls.append((snapshot, operation, kwargs))
        cookies = json.loads(snapshot.cookies)
        uid = "10001" if cookies.get("MUSIC_U") == "synthetic-a" else "20002"
        if snapshot.uid and snapshot.uid != uid:
            raise HubError("binding_changed", "synthetic mismatch", 409)
        if operation == self.gate:
            self.entered.set()
            while not self.release.is_set():
                await asyncio.sleep(0.005)
        if self.error:
            raise self.error
        if operation == "verify":
            return {"uid": uid, "nickname": "synthetic account"}
        return copy.deepcopy(self.results[operation])


@pytest.fixture
def ne(tmp_path):
    settings = Settings(
        instance_id="nas",
        data_dir=tmp_path / "data",
        bridge_url="http://bridge/api/v1",
        public_origin=ORIGIN,
        secure_cookie=False,
        netease_enabled=True,
    )
    protocol, upstream = Protocol(), Upstream({})
    app = create_app(
        settings,
        transport=httpx.MockTransport(upstream),
        netease_protocol=protocol,
        start_worker=False,
    )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as a:
        b = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
        for client, username in [(a, "alice"), (b, "bob")]:
            r = client.post(
                "/api/auth/login",
                json={"username": username, "password": "password"},
            )
            client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        yield app, protocol, a, b
        b.close()


def account(client):
    return next(
        a
        for a in client.get("/api/accounts").json()["items"]
        if a["provider"] == "netease"
    )


def bind(client, cookie=COOKIE):
    attempt = client.post("/api/accounts/netease/login", json={"cookie": cookie})
    assert attempt.status_code == 201, attempt.text
    result = client.post(f"/api/accounts/netease/login/{attempt.json()['id']}/bind")
    assert result.status_code == 200, result.text
    return result.json(), attempt.json()


def unlink(client):
    return client.post(
        "/api/accounts/netease/unlink",
        json={"binding_generation": account(client)["binding_generation"]},
    )


def test_explicit_consent_and_provider_account_isolation(ne):
    app, protocol, a, b = ne
    attempt = a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).json()
    assert attempt["uid"] == "10001"
    assert a.get("/api/catalog/netease/playlists?scope=account").status_code == 409
    assert (
        b.post(f"/api/accounts/netease/login/{attempt['id']}/bind").status_code == 404
    )
    bound = a.post(f"/api/accounts/netease/login/{attempt['id']}/bind").json()
    assert a.post(f"/api/accounts/netease/login/{attempt['id']}/bind").json() == bound
    assert account(b)["state"] == "unbound"
    assert (
        a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).status_code
        == 409
    )
    assert (
        a.post("/api/accounts/qq/unlink", json={"binding_generation": 0}).status_code
        == 409
    )
    with app.state.store.db() as db:
        contents = " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM accounts"))
        attempts = " ".join(
            str(tuple(r)) for r in db.execute("SELECT * FROM account_attempts")
        )
    assert "synthetic-a" not in contents + attempts
    assert "MUSIC_U" not in a.get("/api/accounts").text
    assert "credential" not in json.dumps(attempt)


def test_public_is_anonymous_private_requires_bound_and_download_closed(ne):
    app, protocol, a, b = ne
    data = a.get("/api/catalog/netease/playlists").json()
    assert data["scope"] == "public" and data["account"] is None
    assert data["items"][1]["playlist"] is None
    assert protocol.calls[-1][0].cookies == "{}"
    caps = a.get("/api/me").json()["capabilities"]
    assert caps["public_playlists"] == ["netease"] and caps["download"] == []
    assert "netease" not in caps["search"]
    assert a.get("/api/catalog/netease/recommendations").status_code == 409
    bind(a)
    assert (
        a.get("/api/catalog/netease/playlists?scope=account").json()["items"][0][
            "title"
        ]
        == "private list"
    )
    assert (
        a.get("/api/catalog/netease/recommendations?kind=songs").json()[
            "personalization"
        ]
        == "unverified"
    )
    assert (
        a.get("/api/catalog/netease/recommendations").json()["kind"]
        == "recommend_playlists"
    )
    a.get("/api/catalog/netease/playlists")
    assert protocol.calls[-1][0].cookies == "{}"


def test_order_unknown_duplicates_paging_local_favorite(ne):
    app, protocol, a, b = ne
    bind(a)
    data = a.get("/api/catalog/netease/playlists/77?scope=account&page=2").json()
    assert data["page"] == 2 and data["source_total"] == 103 and not data["has_more"]
    assert data["integrity"] == "page_only" and not data["complete"]
    assert [s["source_position"] for s in data["items"]] == [100, 101, 102]
    assert data["items"][0] == {**data["items"][2], "source_position": 100}
    assert data["items"][1]["track"] is None
    track = data["items"][0]["track"]
    assert (
        a.post("/api/favorites", json={"track": track, "enabled": True}).status_code
        == 200
    )
    assert (
        b.post("/api/favorites", json={"track": track, "enabled": True}).status_code
        == 404
    )
    assert unlink(a).status_code == 200
    assert len(a.get("/api/favorites").json()["items"]) == 1
    with app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM songs").fetchone()[0] == 0


@pytest.mark.parametrize(
    "code,status",
    [
        ("platform_auth_required", 409),
        ("binding_changed", 409),
        ("rate_limited", 429),
        ("platform_unavailable", 503),
        ("upstream_contract", 502),
    ],
)
def test_failure_semantics_no_anonymous_fallback_or_fn_logout(ne, code, status):
    app, protocol, a, b = ne
    bind(a)
    protocol.error = HubError(code, "synthetic failure", status)
    result = a.get("/api/catalog/netease/recommendations")
    assert result.status_code == status
    assert a.get("/api/me").status_code == 200
    assert protocol.calls[-1][1] == "recommend_playlists"
    assert account(a)["state"] == (
        "expired" if code in {"platform_auth_required", "binding_changed"} else "bound"
    )


def test_same_uid_rotation_preserves_ref_and_generation_rejects_account_switch(ne):
    app, protocol, a, b = ne
    bound, _ = bind(a)
    result = a.post(
        "/api/accounts/netease/credential",
        json={
            "cookie": COOKIE + "; NMTID=new",
            "binding_generation": bound["binding_generation"],
        },
    )
    assert result.status_code == 200
    rotated = result.json()
    assert (
        rotated["account_ref"] == bound["account_ref"]
        and rotated["binding_generation"] == bound["binding_generation"]
    )
    assert rotated["credential_revision"] == 2
    result = a.post(
        "/api/accounts/netease/credential",
        json={
            "cookie": "MUSIC_U=synthetic-b",
            "binding_generation": bound["binding_generation"],
        },
    )
    assert result.status_code == 409 and account(a) == rotated
    assert unlink(a).status_code == 200
    rebound, _ = bind(a, "MUSIC_U=synthetic-b")
    assert (
        rebound["uid"] == "20002"
        and rebound["binding_generation"] > bound["binding_generation"]
    )


@pytest.mark.parametrize("mutation", ["unlink", "rebind", "rotate", "logout"])
def test_late_private_reads_never_publish_or_cache(ne, mutation):
    app, protocol, a, b = ne
    bound, _ = bind(a)
    protocol.gate = "recommend_songs"
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(a.get, "/api/catalog/netease/recommendations?kind=songs")
        assert protocol.entered.wait(3)
        if mutation in {"unlink", "rebind"}:
            assert unlink(a).status_code == 200
            if mutation == "rebind":
                bind(a, "MUSIC_U=synthetic-b")
        elif mutation == "rotate":
            assert (
                a.post(
                    "/api/accounts/netease/credential",
                    json={
                        "cookie": COOKIE + "; NMTID=new",
                        "binding_generation": bound["binding_generation"],
                    },
                ).status_code
                == 200
            )
        else:
            assert a.post("/api/auth/logout").status_code == 200
        protocol.release.set()
        result = pending.result(timeout=3)
    assert result.status_code in {401, 409}
    assert "song-" not in result.text
    with app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM songs").fetchone()[0] == 0


def test_two_users_concurrent_frozen_credentials_and_logout_bound_persists(ne):
    app, protocol, a, b = ne
    bind(a)
    bind(b, "MUSIC_U=synthetic-b")
    protocol.gate = "recommend_songs"
    with ThreadPoolExecutor() as pool:
        first = pool.submit(a.get, "/api/catalog/netease/recommendations?kind=songs")
        assert protocol.entered.wait(3)
        second = pool.submit(b.get, "/api/catalog/netease/recommendations?kind=songs")
        protocol.release.set()
        result_a, result_b = first.result(3), second.result(3)
    assert result_a.status_code == result_b.status_code == 200
    assert result_a.json()["account"]["uid"] == "10001"
    assert result_b.json()["account"]["uid"] == "20002"
    assert a.post("/api/auth/logout").status_code == 200
    owner = Principal(instance_id="nas", user_guid="user-a")
    assert app.state.netease_accounts.store.get(owner)["state"] == "bound"


def test_candidate_logout_revokes_only_netease_attempt(ne):
    app, protocol, a, b = ne
    attempt = a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).json()
    assert a.post("/api/auth/logout").status_code == 200
    r = a.post("/api/auth/login", json={"username": "alice", "password": "password"})
    a.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    assert (
        a.post(f"/api/accounts/netease/login/{attempt['id']}/bind").status_code == 404
    )
    assert (
        a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).status_code
        == 201
    )


@pytest.mark.parametrize(
    "cookie",
    [
        "",
        "abc",
        "MUSIC_A=anonymous",
        "MUSIC_U=x\nBad: yes",
        'MUSIC_U="bad value"',
        "MUSIC_U=" + "x" * 16400,
    ],
)
def test_reject_invalid_cookies_without_platform_call(ne, cookie):
    app, protocol, a, b = ne
    result = a.post("/api/accounts/netease/login", json={"cookie": cookie})
    assert result.status_code in {400, 422}
    assert not protocol.calls
    assert cookie not in result.text if cookie else True


@pytest.mark.parametrize(
    "path",
    [
        "playlists?page=0",
        "playlists?page=101",
        "playlists/abc",
        "playlists/0",
        "playlists/" + "9" * 5000,
        "playlists/77?page=0",
        "playlists?scope=shared",
        "recommendations?kind=daily",
        "recommendations?page=35",
    ],
)
def test_bad_catalog_inputs_are_rejected(ne, path):
    app, protocol, a, b = ne
    assert a.get("/api/catalog/netease/" + path).status_code in {400, 422}
    assert not protocol.calls


def test_csrf_failed_validation_releases_attempt_and_retry(ne):
    app, protocol, a, b = ne
    assert (
        a.post(
            "/api/accounts/netease/login",
            json={"cookie": COOKIE},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    protocol.error = HubError("platform_unavailable", "synthetic", 503)
    assert (
        a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).status_code
        == 503
    )
    protocol.error = None
    bind(a)


def test_cookie_filter_does_not_import_foreign_headers():
    assert json.loads(parse_cookie(COOKIE + "; other=private")) == {
        "MUSIC_U": "synthetic-a",
        "__csrf": "synthetic-csrf",
    }


@pytest.mark.parametrize("stage", ["begin", "bind"])
def test_binding_transactions_roll_back_and_can_retry_without_restart(ne, stage):
    app, protocol, a, b = ne
    attempt = None
    if stage == "bind":
        attempt = a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).json()
    with app.state.store.db() as db:
        db.execute(
            "CREATE TRIGGER reject_attempt BEFORE INSERT ON account_attempts BEGIN SELECT RAISE(FAIL,'synthetic disk failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        if stage == "begin":
            a.post("/api/accounts/netease/login", json={"cookie": COOKIE})
        else:
            a.post(f"/api/accounts/netease/login/{attempt['id']}/bind")
    assert account(a)["state"] == "unbound"
    with app.state.store.db() as db:
        db.execute("DROP TRIGGER reject_attempt")
    if stage == "begin":
        bind(a)
    else:
        assert (
            a.post(f"/api/accounts/netease/login/{attempt['id']}/bind").status_code
            == 200
        )


def test_late_failed_old_request_cannot_expire_new_binding(ne):
    app, protocol, a, b = ne
    bind(a)
    protocol.gate = "recommend_songs"
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(a.get, "/api/catalog/netease/recommendations?kind=songs")
        assert protocol.entered.wait(3)
        unlink(a)
        new, _ = bind(a, "MUSIC_U=synthetic-b")
        protocol.error = HubError(
            "platform_auth_required", "synthetic old failure", 409
        )
        protocol.release.set()
        assert pending.result(3).status_code == 409
    assert account(a) == new


def test_invalid_page_does_not_cache_and_netease_download_is_rejected(ne):
    app, protocol, a, b = ne
    assert a.get("/api/catalog/netease/playlists/77").status_code == 409
    with app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM songs").fetchone()[0] == 0
    page = a.get("/api/catalog/netease/playlists/77?page=2").json()
    manifest = a.post(
        "/api/manifests", json={"tracks": [page["items"][0]["track"]]}
    ).json()
    result = a.post(
        "/api/tasks",
        json={"manifest_id": manifest["id"]},
        headers={"Idempotency-Key": "synthetic-ne-denied"},
    )
    assert result.status_code == 409 and result.json()["error"]["code"] == "unsupported"
    assert a.post("/api/catalog/netease/favorites", json={}).status_code == 404
    assert not a.get("/api/tasks").json()["items"]


@pytest.mark.parametrize("operation", ["bind", "rotate"])
def test_late_credential_verification_cannot_restore_unlinked_account(ne, operation):
    app, protocol, a, b = ne
    if operation == "bind":
        attempt = a.post("/api/accounts/netease/login", json={"cookie": COOKIE}).json()
        path = f"/api/accounts/netease/login/{attempt['id']}/bind"
        body = {}
    else:
        bound, _ = bind(a)
        path = "/api/accounts/netease/credential"
        body = {
            "cookie": COOKIE + "; NMTID=new",
            "binding_generation": bound["binding_generation"],
        }
    protocol.gate = "verify"
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(a.post, path, json=body)
        assert protocol.entered.wait(3)
        assert unlink(a).status_code == 200
        protocol.release.set()
        assert pending.result(3).status_code in {404, 409}
    assert account(a)["state"] == "unbound"
    assert a.get("/api/catalog/netease/recommendations").status_code == 409


def test_disabled_netease_does_not_require_or_import_sdk(tmp_path, monkeypatch):
    from modules.catalog.netease import NeteaseProtocol

    monkeypatch.setattr(NeteaseProtocol, "available", staticmethod(lambda: False))
    settings = Settings(
        instance_id="nas",
        data_dir=tmp_path / "data",
        bridge_url="http://bridge/api/v1",
        public_origin=ORIGIN,
        secure_cookie=False,
    )
    app = create_app(
        settings, transport=httpx.MockTransport(Upstream({})), start_worker=False
    )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        result = client.post(
            "/api/auth/login", json={"username": "alice", "password": "password"}
        )
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        caps = client.get("/api/me").json()["capabilities"]
        assert caps["public_playlists"] == caps["cloud_accounts"] == []
        assert client.get("/api/accounts").json() == {"enabled": False, "items": []}
        assert client.get("/api/catalog/netease/playlists").status_code == 409
        assert (
            client.post(
                "/api/accounts/netease/login", json={"cookie": COOKIE}
            ).status_code
            == 409
        )
    with pytest.raises(RuntimeError, match="pinned optional MusicBox"):
        create_app(
            settings.model_copy(update={"netease_enabled": True}), start_worker=False
        )
