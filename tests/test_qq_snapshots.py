"""Synthetic platform + real HTTP ownership/SQLite. No real QQ or NAS acceptance."""

import asyncio
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from test_accounts import qq as qq
from test_accounts import raw_track
from test_core import ORIGIN

from hub.app import create_app
from hub.domain import Principal, digest
from hub.errors import HubError
from hub.store import Store

SOURCE = "/api/catalog/qq/playlists/77/snapshots?dirid=9"
OWNER = Principal(instance_id="nas", user_guid="user-a")


class Pages:
    def __init__(self, count=205):
        self.rows = [raw_track(i + 1) for i in range(count)]
        self.calls, self.hook = [], None
        self.entered, self.release = threading.Event(), threading.Event()
        self.gate = None

    async def read(self, snapshot, operation, **kwargs):
        assert operation == "playlist_page"
        page = kwargs["page"]
        call = len(self.calls) + 1
        self.calls.append((snapshot.uin, page))
        if call == self.gate:
            self.entered.set()
            while not self.release.is_set():
                await asyncio.sleep(0.005)
        start = (page - 1) * 100
        rows = copy.deepcopy(self.rows[start : start + 100])
        result = {
            "songlist": rows,
            "songlist_size": len(rows),
            "total_song_num": len(self.rows),
            "hasmore": int(start + len(rows) < len(self.rows)),
            "dirinfo": {"id": 77, "dirid": 9, "title": "synthetic playlist"},
        }
        if self.hook:
            self.hook(call, snapshot, result)
        return result


def setup(qq, count=205):
    bound, _ = qq.bind()
    pages = Pages(count)
    qq.app.state.qq_catalog.protocol = pages
    return bound, pages


def begin(client, key="capture-1", source=SOURCE):
    result = client.post(source, headers={"Idempotency-Key": key})
    assert result.status_code == 201, result.text
    return result.json()


def run(client, capture):
    return client.post(f"/api/playlist-captures/{capture['id']}/run")


def no_manifest(qq):
    with qq.app.state.store.db() as db:
        assert db.execute("SELECT count(*) FROM manifests").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM songs").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0


@pytest.mark.parametrize("count", [0, 1, 100, 101, 205, 1000])
def test_complete_bounded_snapshots_preserve_order_duplicates_unknown_and_hash(
    qq, count
):
    _, pages = setup(qq, count)
    if count > 3:
        pages.rows[1] = copy.deepcopy(pages.rows[0])
        pages.rows[2] = {
            "title": "不可识别曲目",
            "cookie": "must-not-persist",
            "future": 7,
        }
        pages.rows[3] = None
    capture = begin(qq.a)
    assert capture["status"] == "pending"
    result = run(qq.a, capture)
    assert result.status_code == 200, result.text
    completed = result.json()
    assert completed["complete"] and completed["fetched_count"] == count
    manifest = qq.a.get(f"/api/manifests/{completed['manifest_id']}").json()
    assert manifest["source_total"] == manifest["fetched_count"] == count
    assert manifest["integrity"] == "double_read_verified"
    assert manifest["source"]["version"] is None
    assert manifest["source"]["verification"]["atomic"] is False
    entries = manifest["ordered_entries"]
    assert [e["position"] for e in entries] == list(range(count))
    assert len({e["occurrence_id"] for e in entries}) == count
    assert manifest["content_hash"] == digest(
        {k: v for k, v in manifest.items() if k != "content_hash"}
    )
    assert "must-not-persist" not in str(manifest)
    if count > 3:
        assert entries[0]["song"]["track"] == entries[1]["song"]["track"]
        assert (
            entries[2]["song"]["track"] is None and entries[3]["song"]["track"] is None
        )
        assert entries[2]["song"]["raw_metadata"] == {"title": "不可识别曲目"}
        assert entries[2]["song"]["source_hash"] != entries[3]["song"]["source_hash"]
    expected = list(range(1, max(1, (count + 99) // 100) + 1)) * 2
    assert [page for _, page in pages.calls] == expected
    # Same request and repeated run return the frozen result, no new reads/task.
    assert begin(qq.a) == completed
    pages.rows.reverse()
    assert run(qq.a, capture).json() == completed
    assert [page for _, page in pages.calls] == expected
    restarted = Store(qq.settings.data_dir)
    assert restarted.manifest(OWNER, completed["manifest_id"]) == manifest
    for client in (qq.a, qq.b):
        result = client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "qq-disabled"},
            json={"manifest_id": completed["manifest_id"]},
        )
        assert result.status_code == (409 if client == qq.a else 404)
    with restarted.db() as db:
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0


@pytest.mark.parametrize(
    "change",
    [
        "total",
        "reorder",
        "same_count_replace",
        "unknown",
        "metadata",
        "truncated",
        "hasmore",
        "size",
        "identity",
        "missing_more",
    ],
)
def test_paging_drift_and_inconsistent_counts_never_publish_manifest(qq, change):
    _, pages = setup(qq)

    def hook(call, snapshot, result):
        if call != (
            2
            if change
            in {"total", "truncated", "hasmore", "size", "identity", "missing_more"}
            else 4
        ):
            return
        if change == "total":
            result["total_song_num"] += 1
        elif change == "reorder":
            result["songlist"].reverse()
        elif change == "same_count_replace":
            result["songlist"][5] = raw_track(777)
        elif change == "unknown":
            result["songlist"][5] = {"unexpected": "new value"}
        elif change == "metadata":
            result["dirinfo"]["title"] = "changed"
        elif change == "truncated":
            result["songlist"].pop()
            result["songlist_size"] -= 1
        elif change == "hasmore":
            result["hasmore"] = 0
        elif change == "size":
            result["songlist_size"] += 1
        elif change == "identity":
            result["dirinfo"]["id"] = 999
        else:
            del result["hasmore"]

    pages.hook = hook
    result = run(qq.a, begin(qq.a)).json()
    assert result["status"] == "incomplete" and not result["complete"]
    assert result["manifest_id"] is None
    assert result["error"]["code"] in {
        "snapshot_changed",
        "incomplete",
        "upstream_contract",
    }
    no_manifest(qq)


@pytest.mark.parametrize(
    "failure",
    ["timeout", "rate_limited", "platform_unavailable", "platform_auth_required"],
)
def test_failure_stops_without_retries_and_explicit_retry_starts_both_passes(
    qq, failure
):
    _, pages = setup(qq)

    def hook(call, snapshot, result):
        if call == 2:
            if failure == "timeout":
                raise TimeoutError("never expose upstream secrets")
            raise HubError(
                failure,
                "safe synthetic error",
                409 if failure == "platform_auth_required" else 503,
            )

    pages.hook = hook
    capture = begin(qq.a)
    response = run(qq.a, capture)
    assert response.status_code == (409 if failure == "platform_auth_required" else 200)
    status = qq.a.get(f"/api/playlist-captures/{capture['id']}").json()
    assert not status["complete"] and status["fetched_count"] == 100
    assert len(pages.calls) == 2
    assert "never expose" not in response.text
    no_manifest(qq)
    if failure == "platform_auth_required":
        assert qq.a.get("/api/accounts").json()["items"][0]["state"] == "expired"
        assert qq.a.get("/api/me").status_code == 200
        return
    if failure == "rate_limited":
        assert run(qq.a, capture).status_code == 429
        assert len(pages.calls) == 2
        # Advance this persisted deadline, without sleeping or bypassing production retry logic.
        status["retry_at"] = 0
        qq.app.state.store.save_capture(OWNER, status)
    result = run(qq.a, capture).json()
    assert result["complete"] and result["attempt"] == 2
    assert [page for _, page in pages.calls[2:]] == [1, 2, 3, 1, 2, 3]


@pytest.mark.parametrize("change", ["unlink", "rotate", "switch", "logout", "identity"])
def test_inflight_capture_revocation_discards_all_pages_and_never_caches(qq, change):
    bound, pages = setup(qq)
    capture = begin(qq.a)
    pages.gate = 4  # first page of verification scan
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(run, qq.a, capture)
        assert pages.entered.wait(3)
        try:
            if change == "unlink":
                assert (
                    qq.a.post(
                        "/api/accounts/qq/unlink",
                        json={"binding_generation": bound["binding_generation"]},
                    ).status_code
                    == 200
                )
            elif change in {"rotate", "switch"}:
                qq.credentials(
                    uin="20002" if change == "switch" else "10001", token="rotated-key"
                )
            elif change == "logout":
                assert qq.a.post("/api/auth/logout").status_code == 200
            else:
                qq.upstream.owner_override = "user-b"
        finally:
            pages.release.set()
        response = pending.result(5)
    assert response.status_code in (401, 409), response.text
    assert "song-" not in response.text
    no_manifest(qq)
    capture = qq.app.state.store.capture(OWNER, capture["id"])
    assert not capture["complete"] and capture["status"] == "incomplete"


def test_two_users_parallel_capture_and_cross_user_endpoints_are_isolated(qq):
    qq.bind(qq.b, uin="20002", user="user-b")
    _, pages = setup(qq, 101)

    def hook(call, snapshot, result):
        for row in result["songlist"]:
            row["title"] = f"private-{snapshot.uin}"

    pages.hook = hook
    a, b = begin(qq.a), begin(qq.b)  # same idempotency key, different owners
    with ThreadPoolExecutor() as pool:
        fa, fb = pool.submit(run, qq.a, a), pool.submit(run, qq.b, b)
        done_a, done_b = fa.result(5).json(), fb.result(5).json()
    assert done_a["complete"] and done_b["complete"]
    for client, own, other in ((qq.a, done_a, done_b), (qq.b, done_b, done_a)):
        assert client.get(f"/api/manifests/{other['manifest_id']}").status_code == 404
        assert client.get(f"/api/playlist-captures/{other['id']}").status_code == 404
        assert run(client, other).status_code == 404
        listing = client.get(SOURCE).json()["items"]
        assert [x["id"] for x in listing] == [own["id"]]
        manifest = client.get(f"/api/manifests/{own['manifest_id']}").json()
        assert {e["song"]["title"] for e in manifest["ordered_entries"]} == {
            f"private-{own['account']['uin']}"
        }


def test_restart_recovers_interrupted_handle_but_restarts_from_page_one(qq):
    _, pages = setup(qq, 101)
    capture = begin(qq.a)
    # Durable state left by a process killed after a partial pass.
    capture.update(
        status="reading", fetched_count=100, source_total=101, attempt=1, **{"pass": 1}
    )
    qq.app.state.store.save_capture(OWNER, capture)
    app = create_app(
        qq.settings,
        transport=httpx.MockTransport(qq.upstream),
        start_worker=False,
        qq_protocol=pages,
    )
    client = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    try:
        qq.login(client, "alice")
        recovered = client.get(f"/api/playlist-captures/{capture['id']}").json()
        assert (
            recovered["status"] == "incomplete"
            and recovered["error"]["code"] == "interrupted"
        )
        pages.rows[0] = raw_track(888)
        complete = run(client, capture).json()
        assert complete["complete"] and complete["attempt"] == 2
        assert [p for _, p in pages.calls] == [1, 2, 1, 2]
        assert (
            client.get(f"/api/manifests/{complete['manifest_id']}").json()[
                "ordered_entries"
            ][0]["song"]["track"]["id"]
            == "mid888"
        )
    finally:
        client.close()


def test_capture_creation_conflict_capacity_and_csrf(qq):
    _, pages = setup(qq, 1001)
    capture = begin(qq.a)
    assert (
        qq.a.post(
            SOURCE.replace("77", "78"), headers={"Idempotency-Key": "capture-1"}
        ).status_code
        == 409
    )
    assert (
        qq.a.post(
            SOURCE, headers={"Idempotency-Key": "new", "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert qq.a.post(SOURCE).status_code == 400
    assert (
        qq.a.post(
            SOURCE.replace("77", "abc"), headers={"Idempotency-Key": "new"}
        ).status_code
        == 400
    )
    result = run(qq.a, capture).json()
    assert result["error"]["code"] == "capacity_exceeded" and len(pages.calls) == 1
    no_manifest(qq)


def test_manifest_bytes_limit_rejects_without_truncating_unknowns(qq):
    _, pages = setup(qq, 1000)
    for row in pages.rows:
        row["title"] = "长标题" * 170
    result = run(qq.a, begin(qq.a)).json()
    assert result["error"]["code"] == "capacity_exceeded" and not result["complete"]
    no_manifest(qq)


def test_concurrent_same_owner_run_is_not_a_second_scan(qq):
    _, pages = setup(qq)
    capture = begin(qq.a)
    pages.gate = 1
    with ThreadPoolExecutor() as pool:
        first = pool.submit(run, qq.a, capture)
        assert pages.entered.wait(3)
        try:
            assert run(qq.a, capture).status_code == 409
            assert len(pages.calls) == 1
        finally:
            pages.release.set()
        assert first.result(5).json()["complete"]


def test_refresh_before_resume_restarts_with_new_revision_but_rebind_is_rejected(qq):
    bound, pages = setup(qq)
    capture = begin(qq.a)
    qq.credentials(token="new-token")
    complete = run(qq.a, capture).json()
    assert complete["complete"] and complete["account"]["credential_revision"] == 2
    assert complete["account"]["binding_generation"] == bound["binding_generation"]
    other = begin(qq.a, "second")
    assert (
        qq.a.post(
            "/api/accounts/qq/unlink",
            json={"binding_generation": bound["binding_generation"]},
        ).status_code
        == 200
    )
    qq.bind()
    assert run(qq.a, other).status_code == 409
    # Previously imported immutable local snapshot remains owned by the fnOS user.
    assert qq.a.get(f"/api/manifests/{complete['manifest_id']}").status_code == 200


def test_rate_limit_cooldown_survives_restart_and_cannot_be_bypassed_with_new_capture(
    qq,
):
    _, pages = setup(qq)

    def limited(call, snapshot, result):
        raise HubError("rate_limited", "safe limit", 429)

    pages.hook = limited
    first = run(qq.a, begin(qq.a)).json()
    second = begin(qq.a, "new-handle")
    assert run(qq.a, second).status_code == 429
    assert Store(qq.settings.data_dir).capture_retry_at(OWNER) == first["retry_at"]
    assert len(pages.calls) == 1


@pytest.mark.parametrize("budget", ["PAGE_SECONDS", "CAPTURE_SECONDS"])
def test_actual_async_timeout_cancels_platform_read_and_leaves_recoverable_record(
    qq, monkeypatch, budget
):
    _, pages = setup(qq)
    import modules.catalog.qq_snapshot as module

    monkeypatch.setattr(module, budget, 0.02)
    pages.gate = 2
    capture = begin(qq.a)
    result = run(qq.a, capture).json()
    assert result["error"]["code"] == "platform_unavailable"
    assert not result["complete"] and len(pages.calls) <= 2
    assert not qq.app.state.qq_snapshots.active
    no_manifest(qq)


def test_cancelled_capture_keeps_handle_and_no_partial_manifest(qq):
    _, pages = setup(qq)

    def cancel(call, snapshot, result):
        if call == 2:
            raise asyncio.CancelledError()

    pages.hook = cancel
    capture = begin(qq.a)

    async def authenticated():
        pass

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            qq.app.state.qq_snapshots.run(
                OWNER, capture["id"], lambda: None, authenticated
            )
        )
    status = qq.app.state.qq_snapshots.status(OWNER, capture["id"])
    assert status["status"] == "incomplete" and status["error"]["code"] == "interrupted"
    assert not qq.app.state.qq_snapshots.active
    no_manifest(qq)
    assert run(qq.a, capture).json()["complete"]


def test_unknown_to_unknown_change_is_detected_even_when_displayed_placeholders_match(
    qq,
):
    _, pages = setup(qq)
    pages.rows[5] = {"future_metadata": "first"}

    def change(call, snapshot, result):
        if call == 4:
            result["songlist"][5] = {"future_metadata": "second"}

    pages.hook = change
    result = run(qq.a, begin(qq.a)).json()
    assert result["error"]["code"] == "snapshot_changed"
    no_manifest(qq)


def test_metadata_drift_between_pages_is_rejected_even_if_repeated_in_both_scans(qq):
    _, pages = setup(qq)

    def drift(call, snapshot, result):
        if call in (2, 5):
            result["dirinfo"]["title"] = "another title"

    pages.hook = drift
    result = run(qq.a, begin(qq.a)).json()
    assert result["error"]["code"] == "snapshot_changed" and len(pages.calls) == 2
    no_manifest(qq)


def test_completed_manifest_and_existing_task_survive_schema_two_upgrade(qq):
    qq.a.get("/api/search?q=sample")
    m = qq.a.post(
        "/api/manifests",
        json={"tracks": [{"provider": "kuwo", "id_type": "rid", "id": "142276943"}]},
    ).json()
    request = {"manifest_id": m["id"]}
    original = qq.a.post(
        "/api/tasks", headers={"Idempotency-Key": "existing-task"}, json=request
    ).json()
    with qq.app.state.store.db() as db:
        db.execute("DROP TABLE playlist_captures")
        db.execute("PRAGMA user_version=2")
    upgraded = Store(qq.settings.data_dir)
    assert upgraded.manifest(OWNER, m["id"])["content_hash"] == m["content_hash"]
    assert (
        qq.a.post(
            "/api/tasks", headers={"Idempotency-Key": "existing-task"}, json=request
        ).json()
        == original
    )
    with upgraded.db() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert (
        qq.a.get(f"/api/manifests/{m['id']}").status_code == 409
    )  # no new engine DTO disclosure
