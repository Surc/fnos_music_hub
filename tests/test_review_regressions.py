"""Regression cases from the Astra review; synthetic boundaries only."""

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from test_accounts import qq as qq
from test_core import TRACK, raw_song
from test_core import audio as audio
from test_core import rig as rig

import hub.worker
from hub.domain import Principal
from hub.errors import HubError
from hub.store import Store
from hub.worker import Reconciler
from modules.download.assets import open_private
from modules.download.hot import HotEngines


def test_revoke_while_identity_inflight(rig):
    rig.login(rig.a, "alice")
    sid = rig.a.cookies.get("hub_session")
    original = rig.transport.handler

    def revoke(request):
        response = original(request)
        if request.url.path.endswith("/auth/me"):
            rig.app.state.store.logout(sid)
        return response

    rig.transport.handler = revoke
    response = rig.a.get("/api/me")
    print("REVOKED_DURING_IDENTITY", response.status_code)
    assert response.status_code == 401


def test_revoke_while_submit_target_inflight(rig):
    rig.login(rig.a, "alice")
    manifest = rig.manifest(rig.a)
    sid = rig.a.cookies.get("hub_session")
    original = rig.transport.handler

    def revoke(request):
        response = original(request)
        if request.url.path == "/api/settings":
            rig.app.state.store.logout(sid)
        return response

    rig.transport.handler = revoke
    response = rig.submit(rig.a, manifest)
    assert response.status_code == 401
    assert rig.app.state.store.pending() == []


def test_qq_response_after_real_logout(qq):
    qq.bind()
    qq.protocol.gate_operation = "recommend_songs"
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(qq.a.get, "/api/catalog/qq/recommendations?kind=songs")
        assert qq.protocol.entered.wait(2)
        assert qq.a.post("/api/auth/logout", json={}).status_code == 200
        qq.protocol.release.set()
        response = pending.result(3)
    owner = Principal(instance_id="nas", user_guid="user-a")
    with qq.app.state.store.db() as db:
        cached = db.execute(
            "select count(*) from songs where owner=?", (owner.key,)
        ).fetchone()[0]
    assert response.status_code == 401 and cached == 0


def test_logout_releases_attempt_lock(qq):
    qq.start(kind="qr")
    assert qq.a.post("/api/auth/logout", json={}).status_code == 200
    qq.login(qq.a, "alice")
    response = qq.a.post("/api/accounts/qq/login", json={"kind": "qr"})
    print("QR_AFTER_RELOGIN", response.status_code, response.json())
    assert response.status_code == 201


def failed_pair(rig):
    rig.login(rig.a, "alice")
    rig.upstream.search_songs = [raw_song(), raw_song(id=228908, mid="228908")]
    manifest = rig.manifest(rig.a, [TRACK, {**TRACK, "id": "228908"}])
    task = rig.submit(rig.a, manifest).json()
    rig.tick()
    for job in rig.upstream.jobs[8787]:
        job.update(status="error", errorMsg="synthetic failure")
    rig.tick()
    return task


@pytest.mark.parametrize("accepted_before_timeout", [False, True])
def test_partial_retry_stays_recoverable_after_restart(
    rig, monkeypatch, accepted_before_timeout
):
    task = failed_pair(rig)
    engines = rig.app.state.reconciler.engines
    original = engines.call
    calls = []

    async def call(owner, method, path, body=None):
        if method == "POST" and path.endswith("/retry"):
            calls.append(path)
            if len(calls) == 2:
                if accepted_before_timeout:
                    rig.upstream.jobs[8787][1]["status"] = "waiting"
                raise HubError("engine_unavailable", "synthetic lost retry result", 503)
            rig.upstream.jobs[8787][0]["status"] = "waiting"
            return {"retried": True}
        return await original(owner, method, path, body)

    monkeypatch.setattr(engines, "call", call)
    response = rig.a.post(f"/api/tasks/{task['id']}/control", json={"action": "retry"})
    assert response.status_code == 503
    saved = rig.app.state.store.pending()[0]
    assert saved["entries"][0]["status"] == "running"
    assert saved["entries"][1]["status"] == "outcome_unknown"
    restarted = Reconciler(
        Store(rig.settings.data_dir), HotEngines(rig.settings, rig.transport)
    )
    asyncio.run(restarted.tick())
    saved = rig.a.get("/api/tasks").json()["items"][0]
    assert saved["entries"][0]["status"] == "running"
    assert saved["entries"][1]["status"] == (
        "running" if accepted_before_timeout else "failed"
    )
    assert len(calls) == 2 and rig.upstream.creates == 2


def test_retry_false_uses_engine_state(rig, monkeypatch):
    task = failed_pair(rig)
    engines = rig.app.state.reconciler.engines
    original = engines.call

    async def call(owner, method, path, body=None):
        if path.endswith("/retry"):
            return {"retried": False}
        return await original(owner, method, path, body)

    monkeypatch.setattr(engines, "call", call)
    response = rig.a.post(f"/api/tasks/{task['id']}/control", json={"action": "retry"})
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_retry_shared_native_job_updates_both_hub_tasks(rig):
    rig.login(rig.a, "alice")
    manifest = rig.manifest(rig.a)
    first = rig.submit(rig.a, manifest, idem="first").json()
    rig.tick()
    second = rig.submit(rig.a, manifest, idem="second").json()
    rig.tick()
    assert rig.upstream.creates == 1
    rig.upstream.jobs[8787][0]["status"] = "error"
    rig.tick()
    for task in (first, second):
        response = rig.a.post(
            f"/api/tasks/{task['id']}/control", json={"action": "retry"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "running"
    rig.tick()
    assert {t["status"] for t in rig.a.get("/api/tasks").json()["items"]} == {"running"}
    assert sum(p.endswith("/retry") for _, p, _ in rig.upstream.calls) == 1


def test_retry_completed_native_job_revalidates_local_audio(rig, audio):
    rig.login(rig.a, "alice")
    rig.upstream.search_songs = [raw_song(title="Generated test tone", duration=2)]
    task = rig.submit(rig.a).json()
    rig.tick()
    file = rig.settings.users["user-a"].download_root / "test.mp3"
    file.write_text("not audio")
    rig.upstream.jobs[8787][0].update(status="completed", filePath=str(file))
    rig.tick()
    assert rig.a.get("/api/tasks").json()["items"][0]["status"] == "failed"
    assert rig.a.get("/api/assets").json()["items"] == []
    file.write_bytes(audio.read_bytes())
    response = rig.a.post(f"/api/tasks/{task['id']}/control", json={"action": "retry"})
    assert response.status_code == 200 and response.json()["status"] == "running"
    rig.tick()
    assert rig.a.get("/api/tasks").json()["items"][0]["status"] == "completed"
    assert len(rig.a.get("/api/assets").json()["items"]) == 1
    assert not any(p.endswith("/retry") for _, p, _ in rig.upstream.calls)
    assert rig.upstream.creates == 1


@pytest.mark.parametrize("same_user", [False, True])
def test_audio_validation_does_not_block_other_task_control(
    rig, monkeypatch, same_user
):
    rig.login(rig.a, "alice")
    rig.login(rig.b, "bob")
    rig.submit(rig.a)
    client = rig.a if same_user else rig.b
    rig.upstream.search_songs = [raw_song(id=228908, mid="228908")]
    other = rig.manifest(client, [{**TRACK, "id": "228908"}])
    task_b = rig.submit(client, other, idem="second-task").json()
    rig.tick()
    rig.upstream.jobs[8787][0].update(
        status="completed", filePath="/synthetic/ignored.mp3"
    )
    entered, release = threading.Event(), threading.Event()

    def validate(*args):
        entered.set()
        assert release.wait(5)
        raise HubError("invalid_audio", "synthetic validation result", 409)

    monkeypatch.setattr(hub.worker, "validate_audio", validate)

    async def scenario():
        tick = asyncio.create_task(rig.app.state.reconciler.tick())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=rig.app),
                base_url="http://testserver",
                cookies=dict(client.cookies),
                headers={
                    "Origin": "http://testserver",
                    "X-CSRF-Token": client.headers["X-CSRF-Token"],
                },
            ) as api:
                result = await asyncio.wait_for(
                    api.post(
                        f"/api/tasks/{task_b['id']}/control", json={"action": "pause"}
                    ),
                    1,
                )
                assert result.status_code == 200
                assert any(path.endswith("/pause") for _, path, _ in rig.upstream.calls)
                assert not tick.done()
        finally:
            release.set()
            await tick

    asyncio.run(scenario())


def test_parent_symlink_swap_cannot_escape_root(tmp_path, monkeypatch):
    root, outside = tmp_path / "allowed", tmp_path / "outside"
    album = root / "album"
    album.mkdir(parents=True)
    outside.mkdir()
    (album / "song.mp3").write_bytes(b"authorized-file")
    (outside / "song.mp3").write_bytes(b"outside-marker")
    original = os.open

    def swap(path, *args, **kwargs):
        if path == "song.mp3":
            album.rename(root / "original")
            album.symlink_to(outside, target_is_directory=True)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap)
    fd, _ = open_private(root, str(album / "song.mp3"))
    try:
        assert os.read(fd, 64) == b"authorized-file"
    finally:
        os.close(fd)
    with pytest.raises(HubError):
        open_private(root, str(album / "song.mp3"))


def test_special_files_and_parent_traversal_are_rejected(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(HubError):
        open_private(tmp_path, str(fifo))
    with pytest.raises(HubError):
        open_private(tmp_path, str(tmp_path / ".." / "other"))


def test_expired_candidate_does_not_block_new_login(qq):
    qq.start(kind="qr")
    store = qq.app.state.store
    sid = store.session_hash(qq.a.cookies.get("hub_session"))
    with store.db() as db:
        db.execute("UPDATE sessions SET expires=? WHERE id=?", (time.time() - 1, sid))
    qq.login(qq.a, "alice")
    assert qq.a.post("/api/accounts/qq/login", json={"kind": "qr"}).status_code == 201


def test_logout_preserves_bound_account(qq):
    bound, _ = qq.bind()
    assert qq.a.post("/api/auth/logout", json={}).status_code == 200
    qq.login(qq.a, "alice")
    assert (
        qq.a.get("/api/accounts").json()["items"][0]["account_ref"]
        == bound["account_ref"]
    )


def test_logout_old_session_preserves_new_candidate(qq):
    first = qq.start(kind="qr")
    generation = first["binding_generation"]
    assert (
        qq.a.post(
            "/api/accounts/qq/unlink", json={"binding_generation": generation}
        ).status_code
        == 200
    )
    from fastapi.testclient import TestClient

    second = TestClient(
        qq.app, base_url="http://testserver", headers={"Origin": "http://testserver"}
    )
    try:
        qq.login(second, "alice")
        current = qq.start(second, kind="qr")
        assert qq.a.post("/api/auth/logout", json={}).status_code == 200
        response = second.get(f"/api/accounts/qq/login/{current['id']}")
        assert response.status_code == 200 and response.json()["status"] == "waiting"
    finally:
        second.close()


def test_control_rechecks_session_after_waiting_for_task_lock(rig):
    rig.login(rig.a, "alice")
    task = rig.submit(rig.a).json()
    rig.tick()
    sid = rig.a.cookies.get("hub_session")

    async def scenario():
        lock = rig.app.state.reconciler.task_lock(task["id"])
        await lock.acquire()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=rig.app),
            base_url="http://testserver",
            cookies=dict(rig.a.cookies),
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": rig.a.headers["X-CSRF-Token"],
            },
        ) as client:
            pending = asyncio.create_task(
                client.post(
                    f"/api/tasks/{task['id']}/control", json={"action": "pause"}
                )
            )
            await asyncio.sleep(0.03)
            rig.app.state.store.logout(sid)
            lock.release()
            response = await pending
            assert response.status_code == 401
            assert not any(path.endswith("/pause") for _, path, _ in rig.upstream.calls)

    asyncio.run(scenario())


def test_previously_accepted_download_survives_logout(rig):
    rig.login(rig.a, "alice")
    rig.submit(rig.a)
    assert rig.a.post("/api/auth/logout", json={}).status_code == 200
    rig.tick()
    assert rig.upstream.creates == 1


def test_duplicate_occurrences_control_native_job_once(rig):
    rig.login(rig.a, "alice")
    task = rig.submit(rig.a, rig.manifest(rig.a, [TRACK, TRACK])).json()
    rig.tick()
    for action, expected in (("pause", "paused"), ("resume", "running")):
        response = rig.a.post(
            f"/api/tasks/{task['id']}/control", json={"action": action}
        )
        assert response.status_code == 200
        assert response.json()["status"] == expected
        assert {e["status"] for e in response.json()["entries"]} == {expected}
        assert (
            sum(path.endswith("/" + action) for _, path, _ in rig.upstream.calls) == 1
        )


def test_pending_uses_active_index_and_excludes_terminal_history(rig):
    rig.login(rig.a, "alice")
    first = rig.submit(rig.a).json()
    rig.submit(rig.a, idem="second")
    owner = Principal(instance_id="nas", user_guid="user-a")
    task = rig.app.state.store._owned("tasks", owner.key, first["id"])
    task["status"] = "completed"
    rig.app.state.store.save_task(task)
    assert [t["id"] for t in rig.app.state.store.pending()] != [first["id"]]
    assert len(rig.app.state.store.pending()) == 1
    with rig.app.state.store.db() as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT payload FROM tasks INDEXED BY tasks_active WHERE json_extract(payload, '$.status') NOT IN ('completed','failed') ORDER BY rowid"
        ).fetchall()
        assert any("tasks_active" in row[3] for row in plan)
