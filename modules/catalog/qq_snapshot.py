"""Bounded, restartable QQ captures. Partial pages never become download manifests."""

import asyncio
import time

from hub.domain import MAX_MANIFEST_ITEMS, canonical, digest, make_manifest, now
from hub.errors import HubError

from .qq import SDK_COMMIT, song_metadata

PAGE_SIZE = 100
CAPTURE_SECONDS = 120
PAGE_SECONDS = 30


def playlist_ref(playlist_id, dirid):
    if (
        any(
            not value.isascii()
            or not value.isdecimal()
            or len(value) > 20
            or not 0 <= int(value) < 2**64
            for value in (playlist_id, dirid)
        )
        or int(playlist_id) == int(dirid) == 0
    ):
        raise HubError("invalid_request", "歌单引用不合法")
    return {"provider": "qq", "id": str(int(playlist_id)), "dirid": str(int(dirid))}


def entry_metadata(raw, position):
    song = song_metadata(raw, position)
    # Hash the original entry even when the DTO cannot represent it. Never persist
    # arbitrary upstream objects (which can contain signed URLs or credentials).
    song["source_hash"] = digest(raw)
    if song["track"] is None:
        song["raw_metadata"] = {
            key: value[:512] if isinstance(value, str) else value
            for key, value in (raw.items() if isinstance(raw, dict) else [])
            if key in {"id", "mid", "title", "name", "interval"}
            and type(value) in {str, int, bool, type(None)}
        }
    return song


def checked_page(result, source, page, total):
    rows, reported = result.get("songlist"), result.get("total_song_num")
    more, size, info = (
        result.get("hasmore"),
        result.get("songlist_size"),
        result.get("dirinfo"),
    )
    if (
        not isinstance(rows, list)
        or len(rows) > PAGE_SIZE
        or type(reported) is not int
        or reported < 0
        or type(more) not in {int, bool}
        or more not in (0, 1)
        or type(size) is not int
        or size != len(rows)
        or not isinstance(info, dict)
    ):
        raise HubError("upstream_contract", "QQ 分页字段缺失或不符合约定", 502)
    if reported > MAX_MANIFEST_ITEMS:
        raise HubError(
            "capacity_exceeded", "完整快照最多支持 1000 项，不会截断歌单", 413
        )
    # dirid=0 is a request default; QQ may resolve it to the real directory.
    pid = info.get("id", info.get("tid", info.get("dissid")))
    actual_dir = info.get("dirid", info.get("dirId"))
    if (source["id"] != "0" and str(pid) != source["id"]) or (
        source["dirid"] != "0" and str(actual_dir) != source["dirid"]
    ):
        raise HubError("snapshot_changed", "来源返回了不同的歌单引用", 409)
    if total is not None and reported != total:
        raise HubError("snapshot_changed", "分页期间来源总数发生变化", 409)
    start = (page - 1) * PAGE_SIZE
    expected = min(PAGE_SIZE, max(0, reported - start))
    if len(rows) != expected or bool(more) != (start + len(rows) < reported):
        raise HubError("incomplete", "来源总数、页长度或结束标记不一致", 409)
    if len(canonical(result).encode()) > 512 * 1024:
        raise HubError("capacity_exceeded", "来源单页响应超过容量限制", 413)
    # All original entry fields and directory metadata take part in comparison.
    # This is intentionally conservative about metadata changing during capture.
    return (
        rows,
        reported,
        digest({"rows": rows, "info": info, "total": reported, "more": bool(more)}),
    )


class QqSnapshots:
    def __init__(self, catalog):
        self.catalog, self.store = catalog, catalog.store
        self.active = {}  # one capture per owner, no background/platform queue

    def status(self, owner, capture_id):
        capture = self.store.capture(owner, capture_id)
        if capture["status"] == "reading" and self.active.get(owner.key) != capture_id:
            capture.update(
                status="incomplete",
                complete=False,
                error={
                    "code": "interrupted",
                    "message": "上次读取已中断，重试将从第一页重新验证",
                },
            )
        return capture

    async def begin(self, owner, source, idem):
        grant, _ = await self.catalog.accounts.snapshot(owner)
        capture = self.store.begin_capture(owner, source, grant, idem)
        return self.status(owner, capture["id"])

    def remove(self, owner, capture_id):
        self.store.capture(owner, capture_id)  # ownership before conflict details
        if self.active.get(owner.key) == capture_id:
            raise HubError("conflict", "读取进行中，请结束后再删除", 409)
        return self.store.remove_capture(owner, capture_id)

    async def run(self, owner, capture_id, check_session, reauthenticate):
        capture = self.status(owner, capture_id)
        if capture["status"] == "deleted":
            raise HubError("gone", "此快照已删除，请创建新的读取请求", 410)
        if capture["complete"]:
            return capture
        if owner.key in self.active:
            raise HubError("conflict", "此用户已有歌单正在读取，请稍后回读状态", 409)
        if self.store.capture_retry_at(owner) > time.time():
            raise HubError("rate_limited", "请等待快照中的 retry_at 后再显式重试", 429)
        self.active[owner.key] = capture_id
        capture.update(
            status="reading",
            error=None,
            complete=False,
            attempt=capture["attempt"] + 1,
            fetched_count=0,
            source_total=None,
            **{"pass": 0},
            started_at=now(),
        )
        try:
            self.store.save_capture(owner, capture)
            grant, credentials = await self.catalog.accounts.snapshot(owner)
            # A token refresh permits a fresh two-pass attempt, never continuation
            # of old pages. Unlink/rebind or account switch requires a new request.
            if any(
                grant[key] != capture["account"][key]
                for key in ("account_ref", "binding_generation", "uin")
            ):
                raise HubError("binding_changed", "原歌单请求的账号关联已撤销", 409)
            capture["account"] = grant
            songs, hashes, total, header_hash = [], [], None, None
            async with asyncio.timeout(CAPTURE_SECONDS):
                for scan in (1, 2):
                    page, count = 1, 0
                    while True:
                        check_session()
                        async with asyncio.timeout(PAGE_SECONDS):
                            result = await self.catalog.read_bound(
                                owner,
                                grant,
                                credentials,
                                "playlist_page",
                                playlist_id=capture["source"]["id"],
                                dirid=capture["source"]["dirid"],
                                page=page,
                            )
                        check_session()
                        rows, total, page_hash = checked_page(
                            result, capture["source"], page, total
                        )
                        current_header = digest(result["dirinfo"])
                        if header_hash is not None and current_header != header_hash:
                            raise HubError(
                                "snapshot_changed", "分页期间歌单信息发生变化", 409
                            )
                        header_hash = current_header
                        if scan == 1:
                            hashes.append(page_hash)
                            songs.extend(
                                entry_metadata(raw, count + i)
                                for i, raw in enumerate(rows)
                            )
                            if len(canonical(songs).encode()) > 512 * 1024:
                                raise HubError(
                                    "capacity_exceeded", "快照条目超过容量限制", 413
                                )
                        elif page_hash != hashes[page - 1]:
                            raise HubError(
                                "snapshot_changed",
                                "两轮读取的顺序或内容不同，请重新获取",
                                409,
                            )
                        count += len(rows)
                        capture.update(
                            source_total=total, fetched_count=count, **{"pass": scan}
                        )
                        self.store.save_capture(owner, capture)
                        if count == total:
                            break
                        page += 1
                await reauthenticate()
                await self.catalog.accounts.validate(owner, grant, credentials)
                check_session()
                manifest = make_manifest(
                    owner,
                    songs,
                    source={
                        "kind": "remote_playlist",
                        "adapter": "qq-two-pass-v1",
                        "sdk_commit": SDK_COMMIT,
                        "playlist": capture["source"],
                        "account": {
                            key: grant[key]
                            for key in (
                                "account_ref",
                                "binding_generation",
                                "credential_revision",
                            )
                        },
                        "version": None,
                        "verification": {
                            "method": "two_full_reads",
                            "atomic": False,
                            "started_at": capture["started_at"],
                            "page_hashes": hashes,
                        },
                    },
                    integrity="double_read_verified",
                )
                capture.update(
                    status="complete",
                    complete=True,
                    error=None,
                    retry_at=0,
                    finished_at=now(),
                    manifest_id=manifest["snapshot_id"],
                    content_hash=manifest["content_hash"],
                )
                self.store.save_capture(owner, capture, manifest)
                return capture
        except (HubError, TimeoutError) as exc:
            if isinstance(exc, TimeoutError):
                exc = HubError(
                    "platform_unavailable", "歌单读取超时，重试将从第一页开始", 503
                )
            capture.update(
                status="incomplete",
                complete=False,
                finished_at=now(),
                error={"code": exc.code, "message": exc.message},
                retry_at=time.time() + (30 if exc.code == "rate_limited" else 0),
            )
            self.store.save_capture(owner, capture)
            if exc.code in {
                "auth_required",
                "binding_changed",
                "platform_auth_required",
                "forbidden",
            }:
                raise exc
            return capture
        finally:
            # Cancellation/crash cannot promote partial data; restart runs both scans anew.
            try:
                if capture["status"] == "reading":
                    capture.update(
                        status="incomplete",
                        complete=False,
                        error={
                            "code": "interrupted",
                            "message": "读取中断，请从第一页重新验证",
                        },
                    )
                    self.store.save_capture(owner, capture)
            finally:
                # A failed recovery write must never leak the in-memory owner slot.
                self.active.pop(owner.key, None)
