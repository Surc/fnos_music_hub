"""Boundary tests use HTTP contracts, real SQLite and generated audio, not live accounts."""

import asyncio
import copy
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from hub.app import create_app
from hub.config import Settings
from hub.domain import Principal, TrackRef
from hub.errors import HubError
from hub.store import Store
from hub.worker import Reconciler
from modules.download.assets import validate_audio
from modules.download.hot import HotEngines

ORIGIN = "http://testserver"
TRACK = {"provider": "kuwo", "id_type": "rid", "id": "142276943"}


def raw_song(**updates):
    # Pinned Hot search has no platform field on individual results.
    return {
        "id": 142276943,
        "mid": "142276943",
        "mediaMid": "142276943",
        "title": "DAYBREAK'S BELL",
        "artist": "L'Arc～en～Ciel",
        "album": "KISS",
        "duration": 252,
        "qualities": [
            {"quality": "320kmp3", "filename": "320.mp3", "size": 0},
            {"quality": "flac", "filename": "2000.flac", "size": 0},
        ],
        **updates,
    }


class Upstream:
    def __init__(self, roots):
        self.roots, self.calls, self.jobs, self.creates = (
            roots,
            [],
            {8787: [], 8788: []},
            0,
        )
        self.revoked, self.identity_error, self.no_guid = False, False, False
        self.owner_override = None
        self.search_songs, self.timeout_once, self.directory_mismatch = (
            [raw_song()],
            False,
            False,
        )

    def __call__(self, request):
        path = request.url.path
        data = (
            json.loads(request.content)
            if request.content and request.content != b"null"
            else None
        )
        self.calls.append((request.method, path, data))
        if request.url.host == "bridge":
            if path.endswith("/auth/login/password"):
                assert data["password"] == hashlib.sha256(b"password").hexdigest()
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "data": {"userToken": data["username"] + "-secret"},
                    },
                )
            if self.identity_error:
                return httpx.Response(503, json={"error": "offline"})
            if self.revoked:
                return httpx.Response(401, json={"ok": False})
            token = request.headers.get("authorization", "")
            user = self.owner_override or (
                "user-a" if token.endswith("alice-secret") else "user-b"
            )
            return httpx.Response(
                200, json={"ok": True, "data": {} if self.no_guid else {"guid": user}}
            )
        port = request.url.port
        assert request.headers["authorization"].startswith("Bearer ")
        if path == "/api/settings":
            return httpx.Response(
                200,
                json={
                    "revision": 1,
                    "settings": {
                        "downloadDir": "/wrong"
                        if self.directory_mismatch
                        else str(self.roots[port]),
                        "autoDowngrade": False,
                    },
                },
            )
        if path == "/api/music/songs/search":
            return httpx.Response(
                200, json={"songs": self.search_songs, "has_more": False}
            )
        if path == "/api/tasks" and request.method == "GET":
            return httpx.Response(200, json=copy.deepcopy(self.jobs[port]))
        if path == "/api/tasks":
            self.creates += 1
            song = data["song"]
            assert isinstance(song["id"], int) and song["platform"] == "kuwo"
            job = {
                "id": f"job-{self.creates}",
                "platform": song["platform"],
                "songId": song["id"],
                "songMid": song["mid"],
                "quality": data["desiredQuality"],
                "status": "waiting",
                "downloaded": 0,
            }
            self.jobs[port].append(job)
            if self.timeout_once:
                self.timeout_once = False
                raise httpx.ReadTimeout(
                    "simulated lost acknowledgement", request=request
                )
            return httpx.Response(200, json={"outcome": "created", "task": job})
        if path.startswith("/api/tasks/"):
            job_id, action = path.rsplit("/", 2)[1:]
            job = next((j for j in self.jobs[port] if j["id"] == job_id), None)
            if job is None:
                return httpx.Response(404, json={"error": "missing"})
            if action == "retry":
                retried = job["status"] == "error"
                if retried:
                    job["status"] = "waiting"
                return httpx.Response(200, json={"retried": retried})
            allowed = {
                "pause": {"waiting", "downloading"},
                "resume": {"paused", "interrupted"},
            }
            if action not in allowed or job["status"] not in allowed[action]:
                return httpx.Response(400, json={"error": "invalid state"})
            job["status"] = "paused" if action == "pause" else "downloading"
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True})


@pytest.fixture
def rig(tmp_path, monkeypatch):
    roots = {8787: tmp_path / "audio-a", 8788: tmp_path / "audio-b"}
    for root in roots.values():
        root.mkdir()
    monkeypatch.setenv("TEST_A", "a" * 24)
    monkeypatch.setenv("TEST_B", "b" * 24)
    settings = Settings(
        instance_id="nas",
        data_dir=tmp_path / "hub-data",
        bridge_url="http://bridge/api/v1",
        public_origin=ORIGIN,
        secure_cookie=False,
        admin_guids=frozenset({"user-a"}),
        users={
            "user-a": {
                "engine_url": "http://127.0.0.1:8787",
                "engine_token_env": "TEST_A",
                "download_root": roots[8787],
            },
            "user-b": {
                "engine_url": "http://127.0.0.1:8788",
                "engine_token_env": "TEST_B",
                "download_root": roots[8788],
            },
        },
    )
    upstream = Upstream(roots)
    transport = httpx.MockTransport(upstream)
    app = create_app(settings, transport=transport, start_worker=False)
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as a:
        b = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})

        class Rig:
            def login(self, client, name):
                response = client.post(
                    "/api/auth/login", json={"username": name, "password": "password"}
                )
                assert response.status_code == 200, response.text
                client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
                return response

            def manifest(self, client, tracks=None):
                assert (
                    client.get(
                        "/api/search", params={"q": "DAYBREAK'S BELL"}
                    ).status_code
                    == 200
                )
                response = client.post(
                    "/api/manifests", json={"tracks": tracks or [TRACK]}
                )
                assert response.status_code == 201, response.text
                return response.json()["id"]

            def submit(
                self, client, manifest_id=None, idem="test-key", quality="320kmp3"
            ):
                manifest_id = manifest_id or self.manifest(client)
                return client.post(
                    "/api/tasks",
                    json={"manifest_id": manifest_id, "quality": quality},
                    headers={"Idempotency-Key": idem},
                )

            def tick(self):
                asyncio.run(app.state.reconciler.tick())

        r = Rig()
        r.a, r.b, r.app, r.settings, r.upstream, r.transport = (
            a,
            b,
            app,
            settings,
            upstream,
            transport,
        )
        yield r
        b.close()


def test_private_endpoints_require_verified_identity(rig):
    for path in (
        "/api/me",
        "/api/tasks",
        "/api/assets",
        "/api/favorites",
        "/api/admin/injection",
    ):
        assert rig.a.get(path, headers={"X-User-Id": "user-a"}).status_code == 401
    rig.login(rig.a, "alice")
    rig.upstream.no_guid = True
    assert rig.a.get("/api/tasks").status_code == 401
    rig.upstream.no_guid = False
    rig.upstream.identity_error = True
    assert rig.a.get("/api/tasks").status_code == 503
    assert rig.upstream.creates == 0


def test_login_never_returns_or_stores_plain_tokens(rig):
    response = rig.login(rig.a, "alice")
    assert "alice-secret" not in response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    db = rig.settings.data_dir / "hub.sqlite3"
    assert b"alice-secret" not in db.read_bytes() and b"password" not in db.read_bytes()
    assert (db.stat().st_mode & 0o777) == 0o600
    assert ((rig.settings.data_dir / "vault.key").stat().st_mode & 0o777) == 0o600


def test_revocation_owner_change_csrf_and_origin(rig):
    rig.login(rig.a, "alice")
    assert (
        rig.a.post(
            "/api/manifests", json={"tracks": [TRACK]}, headers={"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        rig.a.post(
            "/api/auth/logout", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    rig.upstream.revoked = True
    assert rig.a.get("/api/me").status_code == 401
    rig.upstream.revoked = False
    assert rig.a.post("/api/auth/logout", json={}).status_code == 200
    assert rig.a.get("/api/me").status_code == 401


def test_unknown_search_and_missing_quality_remain_visible(rig):
    rig.login(rig.a, "alice")
    rig.upstream.search_songs = [
        raw_song(qualities=[]),
        {"id": 0},
        raw_song(title="<script>alert(1)</script>"),
    ]
    response = rig.a.get("/api/search", params={"q": "DAYBREAK'S BELL"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert (
        len(items) == 3
        and items[0]["track"] == TRACK
        and items[1]["availability"] == "unknown"
    )
    assert items[0]["qualities"] == []
    assert not any("link" in path for _, path, _ in rig.upstream.calls)
    manifest = rig.a.post("/api/manifests", json={"tracks": [TRACK]}).json()["id"]
    # The third occurrence refreshed this same TrackRef; a different empty-quality song stays unavailable.
    rig.upstream.search_songs = [raw_song(qualities=[])]
    manifest = rig.manifest(rig.a)
    assert rig.submit(rig.a, manifest).status_code == 409


def test_two_users_cannot_read_mutate_or_submit_each_others_records(rig):
    rig.login(rig.a, "alice")
    rig.login(rig.b, "bob")
    manifest = rig.manifest(rig.a)
    assert rig.submit(rig.b, manifest).status_code == 404
    task = rig.submit(rig.a, manifest).json()
    assert rig.b.get("/api/tasks").json()["items"] == []
    assert (
        rig.b.post(
            f"/api/tasks/{task['id']}/control", json={"action": "pause"}
        ).status_code
        == 404
    )
    assert (
        rig.a.post("/api/favorites", json={"track": TRACK, "enabled": True}).status_code
        == 200
    )
    assert len(rig.a.get("/api/favorites").json()["items"]) == 1
    assert rig.b.get("/api/favorites").json()["items"] == []
    assert rig.b.get("/api/admin/injection").status_code == 403
    assert rig.a.get("/api/admin/injection").json()["available"] is False
    assert (
        rig.a.post(
            "/api/manifests", json={"tracks": [TRACK], "owner": "user-b"}
        ).status_code
        == 422
    )


def test_manifest_preserves_order_and_duplicates(rig):
    rig.login(rig.a, "alice")
    id = rig.manifest(rig.a, [TRACK, TRACK])
    owner = Principal(instance_id="nas", user_guid="user-a")
    manifest = rig.app.state.store.manifest(owner, id)
    assert len(manifest["ordered_entries"]) == 2
    assert [e["position"] for e in manifest["ordered_entries"]] == [0, 1]
    assert len({e["occurrence_id"] for e in manifest["ordered_entries"]}) == 2
    rig.submit(rig.a, id).json()
    rig.tick()
    assert rig.upstream.creates == 1
    assert len(rig.a.get("/api/tasks").json()["items"][0]["entries"]) == 2


def test_concurrent_idempotency_and_conflict(rig):
    rig.login(rig.a, "alice")
    manifest = rig.manifest(rig.a)
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: rig.submit(rig.a, manifest), range(12)))
    assert {r.status_code for r in responses} <= {200, 202}
    assert len({r.json()["id"] for r in responses}) == 1
    assert rig.submit(rig.a, manifest, quality="flac").status_code == 409
    rig.tick()
    assert rig.upstream.creates == 1


def test_lost_ack_restarts_without_duplicate_submission(rig):
    rig.login(rig.a, "alice")
    rig.submit(rig.a)
    rig.upstream.timeout_once = True
    rig.tick()
    assert rig.a.get("/api/tasks").json()["items"][0]["status"] == "attention"
    store = Store(rig.settings.data_dir)
    restarted = Reconciler(store, HotEngines(rig.settings, rig.transport))
    asyncio.run(restarted.tick())
    assert rig.upstream.creates == 1
    assert rig.a.get("/api/tasks").json()["items"][0]["status"] == "running"


def test_missing_task_is_unknown_not_resubmitted(rig):
    rig.login(rig.a, "alice")
    rig.submit(rig.a)
    rig.tick()
    rig.upstream.jobs[8787] = []
    rig.tick()
    rig.tick()
    assert rig.upstream.creates == 1
    assert rig.a.get("/api/tasks").json()["items"][0]["status"] == "attention"


def test_wrong_target_never_enqueues(rig):
    rig.login(rig.a, "alice")
    manifest = rig.manifest(rig.a)
    rig.upstream.directory_mismatch = True
    assert rig.submit(rig.a, manifest).status_code == 409
    assert rig.upstream.creates == 0


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "fixture.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-b:a",
            "320k",
            str(path),
        ],
        check=True,
    )
    return path


def test_audio_full_decode_quality_and_sandbox(audio, tmp_path):
    song = {"duration_seconds": 2}
    result = validate_audio(tmp_path, str(audio), song, "320kmp3")
    assert result["codec"] == "mp3" and result["validation"] == "full_decode"
    assert result["sha256"] == hashlib.sha256(audio.read_bytes()).hexdigest()
    for expected in (252,):
        with pytest.raises(HubError):
            validate_audio(
                tmp_path, str(audio), {"duration_seconds": expected}, "320kmp3"
            )
    with pytest.raises(HubError):
        validate_audio(tmp_path, str(audio), song, "flac")
    fake = tmp_path / "error.mp3"
    fake.write_text("<html>error</html>")
    with pytest.raises(HubError):
        validate_audio(tmp_path, str(fake), song, "320kmp3")
    link = tmp_path / "symlink.mp3"
    link.symlink_to(audio)
    with pytest.raises(HubError):
        validate_audio(tmp_path, str(link), song, "320kmp3")
    with pytest.raises(HubError):
        validate_audio(tmp_path / "elsewhere", str(audio), song, "320kmp3")


def test_completed_audio_asset_ownership_and_tampering(rig, audio):
    rig.login(rig.a, "alice")
    rig.login(rig.b, "bob")
    rig.upstream.search_songs = [raw_song(title="Generated test tone", duration=2)]
    rig.submit(rig.a)
    rig.tick()
    file = rig.settings.users["user-a"].download_root / "test.mp3"
    file.write_bytes(audio.read_bytes())
    rig.upstream.jobs[8787][0].update(status="completed", filePath=str(file))
    rig.tick()
    task = rig.a.get("/api/tasks").json()["items"][0]
    assert task["status"] == "completed"
    asset = rig.a.get("/api/assets").json()["items"][0]
    assert asset["index_status"] == "unsupported" and asset["codec"] == "mp3"
    path = f"/api/assets/{asset['id']}/file"
    assert rig.b.get(path).status_code == 404
    assert rig.a.get(path).content == audio.read_bytes()
    file.write_bytes(b"changed")
    assert rig.a.get(path).status_code == 409


def test_request_limit_and_frontend_are_real_files(rig):
    assert rig.a.get("/").status_code == 200
    assert rig.a.get("/static/app.js").status_code == 200
    assert "frame-ancestors 'none'" in rig.a.get("/").headers["content-security-policy"]
    response = rig.a.post(
        "/api/auth/login",
        content=b"x" * 700000,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    response = rig.a.post(
        "/api/auth/login", json={"username": "a", "password": "supersecret", "extra": 1}
    )
    assert response.status_code == 422 and "supersecret" not in response.text


@pytest.mark.parametrize(
    "track",
    [
        {"provider": "qq", "id_type": "rid", "id": "1"},
        {"provider": "kuwo", "id_type": "rid", "id": 142276943},
        {"provider": "kuwo", "id_type": "rid", "id": "0"},
    ],
)
def test_trackref_rejects_ambiguous_identity(track):
    with pytest.raises(ValidationError):
        TrackRef.model_validate(track)


def test_configuration_rejects_shared_engines_and_overlapping_roots(rig):
    data = rig.settings.model_dump()
    data["users"]["user-b"]["engine_url"] = "http://localhost:8787"
    with pytest.raises(ValidationError):
        Settings.model_validate(data)
    data = rig.settings.model_dump()
    data["users"]["user-b"]["download_root"] = (
        data["users"]["user-a"]["download_root"] / "nested"
    )
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_account_identity_change_revokes_the_local_session(rig):
    rig.login(rig.a, "alice")
    rig.upstream.owner_override = "user-b"
    assert rig.a.get("/api/me").status_code == 401
    rig.upstream.owner_override = None
    assert rig.a.get("/api/me").status_code == 401


def test_idempotent_replay_does_not_need_online_engine(rig):
    rig.login(rig.a, "alice")
    manifest = rig.manifest(rig.a)
    accepted = rig.submit(rig.a, manifest).json()
    rig.upstream.directory_mismatch = True
    replay = rig.submit(rig.a, manifest)
    assert replay.status_code == 200 and replay.json()["id"] == accepted["id"]


def test_region_failure_is_explicit_and_search_metadata_remains(rig):
    rig.login(rig.a, "alice")
    rig.submit(rig.a)
    rig.tick()
    rig.upstream.jobs[8787][0].update(
        status="error",
        errorMsg="酷我接口错误: code=407, msg=This resource is not available in your region or country due to copyright protection",
    )
    rig.tick()
    task = rig.a.get("/api/tasks").json()["items"][0]
    assert task["entries"][0]["error"]["code"] == "region_restricted"
    result = rig.a.get("/api/search", params={"q": "DAYBREAK'S BELL"}).json()
    assert result["items"][0]["track"] == TRACK
