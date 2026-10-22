"""Synthetic Hot/QQ contracts, real SQLite and private credential files; no live accounts."""

import asyncio
import base64
import copy
import json
import os
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
from hub.paths import engine_directory

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jxVQAAAAASUVORK5CYII="
)


def raw_track(id=1):
    return {
        "id": id,
        "mid": f"mid{id}",
        "title": f"song-{id}",
        "interval": 252,
        "singer": [{"name": "synthetic artist"}],
        "album": {"name": "synthetic album"},
    }


class Protocol:
    def __init__(self):
        self.calls, self.error, self.gate_operation = [], None, None
        self.entered, self.release = threading.Event(), threading.Event()
        self.results = {
            "verify": {},
            "recommend_playlists": {
                "List": [
                    {
                        "Playlist": {
                            "basic": {"tid": 77, "title": "synthetic recommendation"}
                        }
                    },
                    None,
                ],
                "HasMore": True,
                "FromLimit": 35,
            },
            "recommend_songs": {"tracks": [raw_track(), None, raw_track()]},
            "created_playlists": {
                "v_playlist": [
                    {"tid": 77, "dirid": 9, "dirName": "own list", "songNum": 205}
                ],
                "bFinish": True,
                "total": 1,
            },
            "playlist_page": {
                "dirinfo": {"tid": 77, "dirid": 9, "title": "own list"},
                "songlist": [raw_track(), None, raw_track()],
                "total_song_num": 205,
                "hasmore": 1,
            },
        }

    async def read(self, snapshot, operation, **kwargs):
        self.calls.append((snapshot, operation, kwargs))
        if operation == self.gate_operation:
            self.entered.set()
            while not self.release.is_set():
                await asyncio.sleep(0.005)
        if self.error:
            raise self.error
        return copy.deepcopy(self.results[operation])


@pytest.fixture
def qq(tmp_path, monkeypatch):
    roots = {8787: tmp_path / "a", 8788: tmp_path / "b"}
    for root in roots.values():
        root.mkdir()
    monkeypatch.setenv("QQ_A", "a" * 24)
    monkeypatch.setenv("QQ_B", "b" * 24)
    settings = Settings(
        instance_id="nas",
        data_dir=tmp_path / "data",
        bridge_url="http://bridge/api/v1",
        public_origin=ORIGIN,
        secure_cookie=False,
        qq_accounts_enabled=True,
        users={
            name: {
                "engine_url": f"http://127.0.0.1:{port}",
                "engine_token_env": env,
                "download_root": roots[port],
            }
            for name, port, env in [("user-a", 8787, "QQ_A"), ("user-b", 8788, "QQ_B")]
        },
    )
    upstream, protocol = Upstream(roots), Protocol()
    polls, creates = {}, []

    def transport(request):
        if request.url.path == "/api/login/qr":
            creates.append(request.url.port)
            return httpx.Response(
                200,
                json={
                    "qrcode_id": "synthetic-native-" + str(len(creates)),
                    "qr_base64": base64.b64encode(PNG).decode(),
                },
            )
        if request.url.path.startswith("/api/login/qr/"):
            return httpx.Response(
                200, json=polls.get(request.url.port, {"status": "waiting"})
            )
        return upstream(request)

    app = create_app(
        settings,
        transport=httpx.MockTransport(transport),
        start_worker=False,
        qq_protocol=protocol,
    )
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as a:
        b = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})

        class Rig:
            def login(self, client, username):
                r = client.post(
                    "/api/auth/login",
                    json={"username": username, "password": "password"},
                )
                assert r.status_code == 200, r.text
                client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

            def credentials(
                self,
                user="user-a",
                uin="10001",
                token="synthetic-private-key",
                **kwargs,
            ):
                owner = Principal(instance_id="nas", user_guid=user)
                parent = engine_directory(settings, owner.user_guid)
                parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                os.chmod(parent.parent, 0o700)
                file = parent / "qq-credentials.json"
                file.write_text(
                    json.dumps(
                        {
                            "loginUin": uin,
                            "authst": token,
                            "refreshToken": "synthetic-refresh-not-for-sdk",
                            **kwargs,
                        }
                    )
                )
                file.chmod(0o600)
                return file

            def start(self, client=None, kind="existing"):
                r = (client or a).post("/api/accounts/qq/login", json={"kind": kind})
                assert r.status_code == 201, r.text
                return r.json()

            def bind(self, client=None, uin="10001", user="user-a"):
                self.credentials(user=user, uin=uin)
                attempt = self.start(client)
                r = (client or a).post(f"/api/accounts/qq/login/{attempt['id']}/bind")
                assert r.status_code == 200, r.text
                return r.json(), attempt

        rig = Rig()
        rig.a, rig.b, rig.app, rig.settings, rig.protocol, rig.polls, rig.upstream = (
            a,
            b,
            app,
            settings,
            protocol,
            polls,
            upstream,
        )
        rig.login(a, "alice")
        rig.login(b, "bob")
        yield rig
        b.close()


def test_explicit_binding_and_two_users_never_inherit_native_identity(qq):
    qq.credentials()
    assert qq.a.get("/api/accounts").json()["items"][0]["state"] == "unbound"
    assert qq.a.get("/api/catalog/qq/recommendations").status_code == 409
    bound, attempt = qq.bind()
    assert bound["state"] == "bound" and bound["credential_revision"] == 1
    assert set(bound) == {
        "provider",
        "state",
        "uin",
        "account_ref",
        "binding_generation",
        "credential_revision",
    }
    for suffix in ("", "/qr", "/bind"):
        method = qq.b.post if suffix == "/bind" else qq.b.get
        assert (
            method(f"/api/accounts/qq/login/{attempt['id']}{suffix}").status_code == 404
        )
    assert qq.b.get("/api/catalog/qq/playlists").status_code == 409
    other, _ = qq.bind(qq.b, uin="20002", user="user-b")
    assert bound["account_ref"] != other["account_ref"]
    assert qq.a.get("/api/catalog/qq/playlists").json()["account"]["uin"] == "10001"
    assert qq.b.get("/api/catalog/qq/playlists").json()["account"]["uin"] == "20002"
    assert all(
        "refresh_token" not in snapshot.credential()
        for snapshot, _, _ in qq.protocol.calls
    )
    assert b"synthetic-private-key" not in qq.app.state.store.path.read_bytes()


def test_qr_confirmation_requires_explicit_binding_and_hides_native_secrets(qq):
    attempt = qq.start(kind="qr")
    path = f"/api/accounts/qq/login/{attempt['id']}"
    assert "native" not in json.dumps(attempt)
    assert qq.a.get(path + "/qr").content == PNG
    assert qq.a.post(path + "/bind").status_code == 409
    qq.credentials()
    qq.polls[8787] = {
        "status": "confirmed",
        "credentials": {
            "uin": "10001",
            "authst": "synthetic-private-key",
            "refreshToken": "never-return",
        },
    }
    r = qq.a.get(path)
    assert r.json()["status"] == "confirmed"
    assert "authst" not in r.text and "never-return" not in r.text
    assert qq.a.get("/api/catalog/qq/playlists").status_code == 409
    bound = qq.a.post(path + "/bind")
    assert bound.status_code == 200, bound.text
    assert qq.a.post(path + "/bind").json() == bound.json()
    assert qq.a.get(path + "/qr").status_code == 404
    assert b"synthetic-native" not in qq.app.state.store.path.read_bytes()


def test_late_qr_cannot_rebind_after_unlink_or_logout(qq):
    attempt = qq.start(kind="qr")
    r = qq.a.post(
        "/api/accounts/qq/unlink",
        json={"binding_generation": attempt["binding_generation"]},
    )
    assert r.status_code == 200
    qq.credentials(
        uin="99999"
    )  # A native QR callback may still write after cancellation.
    assert qq.a.post(f"/api/accounts/qq/login/{attempt['id']}/bind").status_code == 404
    assert qq.a.get("/api/accounts").json()["items"][0]["state"] == "unbound"
    new = qq.start()
    assert new["binding_generation"] > attempt["binding_generation"]
    assert qq.a.post("/api/auth/logout").status_code == 200
    qq.login(qq.a, "alice")
    assert qq.a.get(f"/api/accounts/qq/login/{new['id']}").status_code == 404


def test_credentials_rotate_revision_while_account_switch_revokes_generation(qq):
    first, _ = qq.bind()
    qq.credentials(token="synthetic-rotated-key")
    rotated = qq.a.get("/api/accounts").json()["items"][0]
    assert rotated["account_ref"] == first["account_ref"]
    assert rotated["binding_generation"] == first["binding_generation"]
    assert rotated["credential_revision"] == first["credential_revision"] + 1
    qq.credentials(uin="77777")
    revoked = qq.a.get("/api/accounts").json()["items"][0]
    assert revoked["state"] == "binding_changed" and revoked["uin"] is None
    assert revoked["binding_generation"] > rotated["binding_generation"]
    assert qq.a.get("/api/catalog/qq/recommendations").status_code == 409


@pytest.mark.parametrize("change", ["unlink", "rotate", "switch"])
def test_inflight_private_reply_is_discarded_on_binding_or_revision_change(qq, change):
    bound, _ = qq.bind()
    qq.protocol.gate_operation = "recommend_songs"
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(qq.a.get, "/api/catalog/qq/recommendations?kind=songs")
        assert qq.protocol.entered.wait(3)
        try:
            if change == "unlink":
                r = qq.a.post(
                    "/api/accounts/qq/unlink",
                    json={"binding_generation": bound["binding_generation"]},
                )
                assert r.status_code == 200
            else:
                qq.credentials(
                    uin="22222" if change == "switch" else "10001",
                    token="new-private-key",
                )
        finally:
            qq.protocol.release.set()
        r = pending.result(3)
        assert r.status_code == 409 and r.json()["error"]["code"] == "binding_changed"
        assert "song-1" not in r.text
    # Stale responses are not cached into the song store either.
    assert (
        qq.a.post(
            "/api/favorites",
            json={
                "track": {"provider": "qq", "id_type": "songmid", "id": "mid1"},
                "enabled": True,
            },
        ).status_code
        == 404
    )


def test_qq_recommendations_and_pages_preserve_duplicates_unknowns_and_types(qq):
    qq.bind()
    songs = qq.a.get("/api/catalog/qq/recommendations?kind=songs").json()
    assert songs["kind"] == "guess_songs" and songs["personalization"] == "unverified"
    assert songs["items"][0]["track"] == songs["items"][2]["track"]
    assert songs["items"][1]["track"] is None
    assert all(s["qualities"] == [] for s in songs["items"])
    recommendations = qq.a.get("/api/catalog/qq/recommendations").json()
    assert recommendations["kind"] == "recommended_playlists"
    assert recommendations["items"][1]["playlist"] is None
    page = qq.a.get("/api/catalog/qq/playlists/77?dirid=9&page=2").json()
    assert page["source_total"] == 205 and page["page"] == 2
    assert page["complete"] is False and page["integrity"] == "page_only"
    assert page["items"][1]["source_position"] == 101
    assert qq.protocol.calls[-1][2] == {"playlist_id": "77", "dirid": "9", "page": 2}
    assert (
        qq.a.post(
            "/api/favorites",
            json={"track": songs["items"][0]["track"], "enabled": True},
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "code,status",
    [
        ("platform_auth_required", 409),
        ("rate_limited", 429),
        ("platform_unavailable", 503),
    ],
)
def test_platform_errors_never_fall_back_or_log_out_fnos(qq, code, status):
    qq.bind()
    qq.protocol.error = HubError(code, "synthetic safe error", status)
    r = qq.a.get("/api/catalog/qq/recommendations")
    assert r.status_code == status and "items" not in r.json()
    assert qq.a.get("/api/me").status_code == 200
    account = qq.a.get("/api/accounts").json()["items"][0]
    assert account["state"] == (
        "expired" if code == "platform_auth_required" else "bound"
    )


@pytest.mark.parametrize(
    "unsafe", ["mode", "file_symlink", "directory_symlink", "malformed", "oversized"]
)
def test_private_credential_file_boundary(qq, unsafe):
    file = qq.credentials()
    if unsafe == "mode":
        file.chmod(0o644)
    elif unsafe == "file_symlink":
        other = file.with_name("elsewhere.json")
        file.rename(other)
        file.symlink_to(other)
    elif unsafe == "directory_symlink":
        parent = file.parent
        other = parent.with_name("other-directory")
        parent.rename(other)
        parent.symlink_to(other)
    elif unsafe == "malformed":
        file.write_text("[]")
    else:
        file.write_bytes(b"x" * 65537)
    r = qq.a.post("/api/accounts/qq/login", json={"kind": "existing"})
    assert r.status_code == 503 and "synthetic-private-key" not in r.text
    assert "elsewhere" not in r.text


def test_stale_unlink_csrf_invalid_ids_and_restart(qq):
    bound, _ = qq.bind()
    assert (
        qq.a.post("/api/accounts/qq/unlink", json={"binding_generation": 0}).status_code
        == 409
    )
    assert (
        qq.a.post(
            "/api/accounts/qq/unlink",
            json={"binding_generation": bound["binding_generation"]},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code
        == 403
    )
    assert qq.a.get("/api/catalog/qq/playlists/abc").status_code == 400
    assert (
        qq.a.get("/api/catalog/qq/recommendations?kind=songs&page=2").status_code == 400
    )
    from hub.account_store import AccountStore
    from hub.store import Store

    restarted = AccountStore(Store(qq.settings.data_dir))
    assert (
        restarted.get(Principal(instance_id="nas", user_guid="user-a"))["account_ref"]
        == bound["account_ref"]
    )
    assert qq.app.state.store.path.stat().st_mode & 0o777 == 0o600


def test_binding_verification_does_not_commit_after_unlink(qq):
    qq.credentials()
    attempt = qq.start()
    qq.protocol.gate_operation = "verify"
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(qq.a.post, f"/api/accounts/qq/login/{attempt['id']}/bind")
        assert qq.protocol.entered.wait(3)
        try:
            assert (
                qq.a.post(
                    "/api/accounts/qq/unlink",
                    json={"binding_generation": attempt["binding_generation"]},
                ).status_code
                == 200
            )
        finally:
            qq.protocol.release.set()
        assert pending.result(3).status_code == 404
    assert qq.a.get("/api/accounts").json()["items"][0]["state"] == "unbound"


def test_recommendation_uses_upstream_cursor_and_rejects_missing_continuation(qq):
    qq.bind()
    initial = qq.a.get("/api/catalog/qq/recommendations").json()
    assert initial["next_cursor"] == 35
    qq.protocol.results["recommend_playlists"]["FromLimit"] = 80
    result = qq.a.get("/api/catalog/qq/recommendations?page=2&cursor=35")
    assert result.status_code == 200 and result.json()["next_cursor"] == 80
    assert qq.protocol.calls[-1][2] == {"page": 2, "cursor": 35}
    del qq.protocol.results["recommend_playlists"]["FromLimit"]
    assert (
        qq.a.get("/api/catalog/qq/recommendations?page=2&cursor=35").status_code == 502
    )


def test_same_authst_refresh_fields_still_advance_credential_revision(qq):
    first, _ = qq.bind()
    qq.credentials(refreshToken="synthetic-new-refresh")
    current = qq.a.get("/api/accounts").json()["items"][0]
    assert current["binding_generation"] == first["binding_generation"]
    assert current["credential_revision"] == first["credential_revision"] + 1


def test_qr_candidate_must_match_native_credential_identity(qq):
    attempt = qq.start(kind="qr")
    qq.credentials(uin="20002")
    qq.polls[8787] = {
        "status": "confirmed",
        "credentials": {"uin": "10001", "authst": "synthetic-private-key"},
    }
    path = f"/api/accounts/qq/login/{attempt['id']}"
    assert qq.a.get(path).json()["status"] == "error"
    assert qq.a.post(path + "/bind").status_code == 409
    assert qq.a.get("/api/catalog/qq/playlists").status_code == 409


def test_qr_attempt_is_scoped_to_a_single_fnos_session(qq):
    attempt = qq.start(kind="qr")
    other = TestClient(qq.app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    try:
        qq.login(other, "alice")
        path = f"/api/accounts/qq/login/{attempt['id']}"
        assert other.get(path).status_code == 404
        assert other.get(path + "/qr").status_code == 404
        assert other.post(path + "/bind").status_code == 404
    finally:
        other.close()


def test_schema_one_upgrade_preserves_existing_sessions_and_favorites(qq):
    from hub.store import Store

    qq.a.get("/api/search?q=sample")
    track = {"provider": "kuwo", "id_type": "rid", "id": "142276943"}
    assert (
        qq.a.post("/api/favorites", json={"track": track, "enabled": True}).status_code
        == 200
    )
    with qq.app.state.store.db() as db:
        db.execute("DROP TABLE account_attempts")
        db.execute("DROP TABLE accounts")
        db.execute("PRAGMA user_version=1")
    upgraded = Store(qq.settings.data_dir)
    with upgraded.db() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert qq.a.get("/api/me").status_code == 200
    assert qq.a.get("/api/favorites").json()["items"][0]["track"] == track


def test_expired_qr_attempt_cannot_grant_access(qq):
    attempt = qq.start(kind="qr")
    owner = Principal(instance_id="nas", user_guid="user-a")
    session = qq.app.state.store.session(qq.a.cookies.get("hub_session"))
    account_store = qq.app.state.accounts.store
    stored = account_store.attempt(owner, session, attempt["id"])
    stored["expires"] = 0
    account_store.save_attempt(owner, session, stored)
    path = f"/api/accounts/qq/login/{attempt['id']}"
    assert qq.a.get(path).json()["error"]["code"] == "login_expired"
    assert qq.a.get(path + "/qr").status_code == 409
    assert qq.a.post(path + "/bind").status_code == 409
