import asyncio
import fcntl
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from modules.accounts.hot_qq import HotQqCredentials
from modules.accounts.netease import NeteaseAccounts
from modules.catalog.hot import HotCatalog, public_song
from modules.catalog.netease import NeteaseCatalog, NeteaseProtocol
from modules.catalog.qq import QqCatalog, QqProtocol
from modules.catalog.qq_snapshot import QqSnapshots, playlist_ref
from modules.download.assets import open_asset
from modules.download.hot import HotEngines
from modules.fnos.identity import BridgeIdentity

from .accounts import Accounts
from .config import Settings
from .domain import (
    ManifestInput,
    SubmitInput,
    TrackRef,
    make_manifest,
)
from .errors import HubError
from .store import Store
from .worker import Reconciler

COOKIE = "hub_session"


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


class FavoriteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track: TrackRef
    enabled: bool


class ControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "retry"]


class AccountLoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["qr", "existing"] = "qr"


class UnlinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    binding_generation: int = Field(ge=0, strict=True)


class NeteaseLoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cookie: str = Field(min_length=1, max_length=16384)


class NeteaseRotateInput(NeteaseLoginInput):
    binding_generation: int = Field(ge=0, strict=True)


def public_task(task):
    return {
        "id": task["id"],
        "status": task["status"],
        "quality": task["quality"],
        "created_at": task["created_at"],
        "last_error": task.get("last_error"),
        "entries": [
            {
                "track": e["song"]["track"],
                "title": e["song"]["title"],
                "artist": e["song"]["artist"],
                "status": e["status"],
                "error": e["error"],
                "asset_id": e["asset_id"],
                "downloaded_bytes": e.get("downloaded_bytes", 0),
            }
            for e in task["entries"]
        ],
    }


def public_asset(asset):
    return {
        k: v
        for k, v in asset.items()
        if k not in {"file_path", "fingerprint", "runtime_key"}
    }


class BodyLimit:
    def __init__(self, app, limit=600 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        # Buffer only a bounded request; this also covers chunked bodies with no Content-Length.
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                return await JSONResponse(
                    {"error": {"code": "capacity_exceeded", "message": "请求体过大"}},
                    413,
                )(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body"):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(
    settings: Settings,
    *,
    transport=None,
    start_worker=True,
    qq_protocol=None,
    netease_protocol=None,
):
    store = Store(settings.data_dir)
    identity, engines = (
        BridgeIdentity(settings, transport),
        HotEngines(settings, transport),
    )
    catalog = HotCatalog(engines, store)
    protocol = qq_protocol or QqProtocol()
    if (
        settings.qq_accounts_enabled
        and qq_protocol is None
        and not protocol.available()
    ):
        raise RuntimeError(
            "QQ accounts require the pinned optional QQMusicApi dependency"
        )
    accounts = Accounts(settings, store, HotQqCredentials(settings, engines), protocol)
    qq_catalog = QqCatalog(accounts, protocol, store)
    qq_snapshots = QqSnapshots(qq_catalog)
    ne_protocol = netease_protocol or NeteaseProtocol()
    if (
        settings.netease_enabled
        and netease_protocol is None
        and not ne_protocol.available()
    ):
        raise RuntimeError("NetEase requires the pinned optional MusicBox dependency")
    ne_accounts = NeteaseAccounts(settings, store, ne_protocol)
    ne_catalog = NeteaseCatalog(ne_accounts, ne_protocol, store)
    reconciler = Reconciler(store, engines)
    attempts = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        lock = open(settings.data_dir / "instance.lock", "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise RuntimeError(
                "only one Hub process may own this data directory"
            ) from None

        async def watch():
            while True:
                try:
                    await reconciler.tick()
                except Exception as exc:
                    # Do not put upstream response bodies or credentials into logs.
                    import logging

                    logging.getLogger("hub").error(
                        "reconciliation failed: %s", type(exc).__name__
                    )
                await asyncio.sleep(settings.poll_seconds)

        task = asyncio.create_task(watch()) if start_worker else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            lock.close()

    app = FastAPI(
        title="fnOS Music Hub",
        version="0.1.0a1",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store, app.state.reconciler = store, reconciler
    app.state.accounts, app.state.qq_catalog = accounts, qq_catalog
    app.state.qq_snapshots = qq_snapshots
    app.state.netease_accounts, app.state.netease_catalog = ne_accounts, ne_catalog
    app.add_middleware(BodyLimit)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.public_origin).hostname]
    )

    @app.exception_handler(HubError)
    async def hub_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # Pydantic's default error includes submitted input, potentially a password.
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "请求字段或格式不符合接口约定",
                }
            },
            422,
        )

    @app.middleware("http")
    async def request_policy(request, call_next):
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.headers.get("origin") != settings.public_origin
        ):
            return JSONResponse(
                {"error": {"code": "forbidden", "message": "请求来源不匹配"}}, 403
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    async def authenticated(request: Request):
        sid = request.cookies.get(COOKIE)
        session = store.session(sid)
        owner = await identity.current(session["token"])
        store.check_session(session)
        if owner.key != session["owner"]:
            store.logout(sid)
            raise HubError("auth_required", "会话账号归属已变化，请重新登录", 401)
        if request.method not in {"GET", "HEAD"} and not hmac.compare_digest(
            request.headers.get("x-csrf-token", "").encode(), session["csrf"].encode()
        ):
            raise HubError("forbidden", "会话校验未通过，请刷新页面", 403)
        return owner, session

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "version": "0.1.0a1", "stage": "development"}

    @app.post("/api/auth/login")
    async def login(body: LoginInput, request: Request, response: Response):
        ip = request.client.host if request.client else "unknown"
        if len(attempts) > 1000:
            attempts.clear()
        bucket = attempts[ip]
        current = time.monotonic()
        while bucket and bucket[0] < current - 60:
            bucket.popleft()
        if len(bucket) >= 8:
            raise HubError("rate_limited", "登录尝试过于频繁，请稍后再试", 429)
        bucket.append(current)
        device = hashlib.sha256(
            (settings.instance_id + body.username).encode()
        ).hexdigest()[:32]
        owner, token = await identity.login(body.username, body.password, device)
        sid, csrf = store.new_session(owner, token, settings.session_seconds)
        response.set_cookie(
            COOKIE,
            sid,
            max_age=settings.session_seconds,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="strict",
            path="/",
        )
        return {"principal": owner.model_dump(), "csrf_token": csrf}

    @app.post("/api/auth/logout")
    async def logout(
        request: Request, response: Response, context=Depends(authenticated)
    ):
        store.logout(request.cookies[COOKIE])
        response.delete_cookie(
            COOKIE,
            path="/",
            secure=settings.secure_cookie,
            httponly=True,
            samesite="strict",
        )
        # Local session logout does not revoke unrelated official-client sessions.
        return {"ok": True}

    @app.get("/api/me")
    async def me(context=Depends(authenticated)):
        owner, session = context
        cfg = settings.users.get(owner.user_guid)
        return {
            "principal": owner.model_dump(),
            "csrf_token": session["csrf"],
            "is_admin": owner.user_guid in settings.admin_guids,
            "targets": [{"id": "private", "path": str(cfg.download_root)}]
            if cfg
            else [],
            "capabilities": {
                "search": ["kuwo", "qq"] if cfg else [],
                "download": ["kuwo"] if cfg else [],
                "local_favorites": True,
                "recommendations": (["qq"] if accounts.enabled(owner) else [])
                + (["netease"] if ne_accounts.enabled(owner) else []),
                "cloud_accounts": (["qq"] if accounts.enabled(owner) else [])
                + (["netease"] if ne_accounts.enabled(owner) else []),
                "account_playlists": (["qq"] if accounts.enabled(owner) else [])
                + (["netease"] if ne_accounts.enabled(owner) else []),
                "public_playlists": ["netease"] if ne_accounts.enabled(owner) else [],
                "injection": False,
                "indexing": False,
                "playback_feedback": False,
            },
        }

    @app.get("/api/search")
    async def search(
        q: str, provider: str = "kuwo", page: int = 1, context=Depends(authenticated)
    ):
        if not q.strip() or len(q) > 200 or not 1 <= page <= 1000:
            raise HubError("invalid_request", "搜索词或页码不合法")
        return await catalog.search(
            context[0], provider, q.strip(), page, session=context[1]
        )

    @app.get("/api/accounts")
    async def account_status(context=Depends(authenticated)):
        qq = await accounts.status(context[0], context[1])
        ne = await ne_accounts.status(*context)
        return {
            "enabled": qq["enabled"] or ne["enabled"],
            "items": qq["items"] + ne["items"],
        }

    @app.post("/api/accounts/netease/login", status_code=201)
    async def ne_login(body: NeteaseLoginInput, context=Depends(authenticated)):
        return await ne_accounts.start(*context, body.cookie)

    @app.post("/api/accounts/netease/login/{attempt_id}/bind")
    async def ne_bind(attempt_id: str, context=Depends(authenticated)):
        return await ne_accounts.bind(*context, attempt_id)

    @app.post("/api/accounts/netease/unlink")
    async def ne_unlink(body: UnlinkInput, context=Depends(authenticated)):
        return await ne_accounts.unlink(*context, body.binding_generation)

    @app.post("/api/accounts/netease/credential")
    async def ne_rotate(body: NeteaseRotateInput, context=Depends(authenticated)):
        return await ne_accounts.rotate(*context, body.binding_generation, body.cookie)

    @app.get("/api/catalog/netease/playlists")
    async def ne_playlists(
        scope: Literal["public", "account"] = "public",
        page: int = 1,
        context=Depends(authenticated),
    ):
        if not 1 <= page <= 100:
            raise HubError("invalid_request", "网易目录页码不合法")
        return await ne_catalog.page(
            *context,
            "public_playlists" if scope == "public" else "user_playlists",
            scope,
            page,
        )

    @app.get("/api/catalog/netease/recommendations")
    async def ne_recommendations(
        kind: Literal["playlists", "songs"] = "playlists",
        page: int = 1,
        context=Depends(authenticated),
    ):
        if not 1 <= page <= 34:
            raise HubError("invalid_request", "网易推荐页码不合法")
        return await ne_catalog.page(*context, "recommend_" + kind, "account", page)

    @app.get("/api/catalog/netease/playlists/{playlist_id}")
    async def ne_playlist(
        playlist_id: str,
        scope: Literal["public", "account"] = "public",
        page: int = 1,
        context=Depends(authenticated),
    ):
        if (
            not playlist_id.isascii()
            or not playlist_id.isdecimal()
            or not 0 < int(playlist_id) < 10**20
            or not 1 <= page <= 100
        ):
            raise HubError("invalid_request", "网易歌单或页码不合法")
        return await ne_catalog.page(
            *context, "playlist_page", scope, page, playlist_id
        )

    @app.post("/api/accounts/qq/login", status_code=201)
    async def account_login(body: AccountLoginInput, context=Depends(authenticated)):
        return await accounts.start(*context, body.kind)

    @app.get("/api/accounts/qq/login/{attempt_id}")
    async def account_poll(attempt_id: str, context=Depends(authenticated)):
        return await accounts.poll(*context, attempt_id)

    @app.get("/api/accounts/qq/login/{attempt_id}/qr")
    async def account_qr(attempt_id: str, context=Depends(authenticated)):
        return Response(
            await accounts.image(*context, attempt_id), media_type="image/png"
        )

    @app.post("/api/accounts/qq/login/{attempt_id}/bind")
    async def account_bind(attempt_id: str, context=Depends(authenticated)):
        return await accounts.bind(*context, attempt_id)

    @app.post("/api/accounts/qq/unlink")
    async def account_unlink(body: UnlinkInput, context=Depends(authenticated)):
        return await accounts.unlink(context[0], body.binding_generation, context[1])

    @app.get("/api/catalog/qq/recommendations")
    async def recommendations(
        kind: Literal["playlists", "songs"] = "playlists",
        page: int = 1,
        cursor: int = 0,
        context=Depends(authenticated),
    ):
        if (
            not 1 <= page <= 50
            or not 0 <= cursor <= 100000
            or (kind == "songs" and (page != 1 or cursor != 0))
        ):
            raise HubError("invalid_request", "推荐页码不合法")
        return await qq_catalog.recommendations(
            context[0], kind, page, cursor, session=context[1]
        )

    @app.get("/api/catalog/qq/playlists")
    async def account_playlists(context=Depends(authenticated)):
        return await qq_catalog.playlists(context[0], session=context[1])

    @app.get("/api/catalog/qq/playlists/{playlist_id}")
    async def playlist_page(
        playlist_id: str,
        dirid: str = "0",
        page: int = 1,
        context=Depends(authenticated),
    ):
        playlist_ref(playlist_id, dirid)
        if not 1 <= page <= 100:
            raise HubError("invalid_request", "歌单页码不合法")
        return await qq_catalog.playlist_page(
            context[0], playlist_id, dirid, page, session=context[1]
        )

    @app.post("/api/catalog/qq/playlists/{playlist_id}/snapshots", status_code=201)
    async def create_snapshot(
        playlist_id: str,
        dirid: str = "0",
        idempotency_key: str = Header(default=""),
        context=Depends(authenticated),
    ):
        return await qq_snapshots.begin(
            context[0],
            playlist_ref(playlist_id, dirid),
            idempotency_key,
            session=context[1],
        )

    @app.get("/api/catalog/qq/playlists/{playlist_id}/snapshots")
    async def playlist_snapshots(
        playlist_id: str,
        dirid: str = "0",
        before: str | None = None,
        limit: int = 20,
        context=Depends(authenticated),
    ):
        owner = context[0]
        captures = store.captures(
            owner, playlist_ref(playlist_id, dirid), before, limit
        )
        captures["items"] = [
            qq_snapshots.status(owner, c["id"]) for c in captures["items"]
        ]
        return captures

    @app.get("/api/playlist-captures")
    async def snapshot_history(
        before: str | None = None, limit: int = 20, context=Depends(authenticated)
    ):
        owner = context[0]
        captures = store.captures(owner, before=before, limit=limit)
        captures["items"] = [
            qq_snapshots.status(owner, c["id"]) for c in captures["items"]
        ]
        return captures

    @app.delete("/api/playlist-captures/{capture_id}")
    async def remove_snapshot(capture_id: str, context=Depends(authenticated)):
        return qq_snapshots.remove(context[0], capture_id)

    @app.get("/api/playlist-captures/{capture_id}")
    async def snapshot_status(capture_id: str, context=Depends(authenticated)):
        return qq_snapshots.status(context[0], capture_id)

    @app.post("/api/playlist-captures/{capture_id}/run")
    async def capture_playlist(
        capture_id: str, request: Request, context=Depends(authenticated)
    ):
        def check_session():
            store.session(request.cookies.get(COOKIE))

        async def reauthenticate():
            await authenticated(request)

        return await qq_snapshots.run(
            context[0], capture_id, check_session, reauthenticate
        )

    @app.get("/api/manifests/{manifest_id}")
    async def read_manifest(manifest_id: str, context=Depends(authenticated)):
        manifest = store.manifest(context[0], manifest_id)
        if manifest["source"]["kind"] != "remote_playlist":
            raise HubError("unsupported", "此只读端点仅提供已保存的远端歌单快照", 409)
        return manifest

    @app.get("/api/favorites")
    async def favorites(context=Depends(authenticated)):
        return {
            "items": [
                public_song(s) for s in store.owned_list("favorites", context[0])
            ],
            "kind": "local",
        }

    @app.post("/api/favorites")
    async def favorite(body: FavoriteInput, context=Depends(authenticated)):
        store.favorite(context[0], body.track, body.enabled)
        return {"ok": True, "kind": "local"}

    @app.post("/api/manifests", status_code=201)
    async def manifest(body: ManifestInput, context=Depends(authenticated)):
        owner = context[0]
        manifest = make_manifest(
            owner, [store.song(owner, track) for track in body.tracks]
        )
        store.save_manifest(owner, manifest)
        return {
            "id": manifest["snapshot_id"],
            "content_hash": manifest["content_hash"],
            "complete": True,
            "count": len(manifest["ordered_entries"]),
        }

    @app.post("/api/tasks")
    async def submit(
        body: SubmitInput,
        response: Response,
        idempotency_key: str = Header(default=""),
        context=Depends(authenticated),
    ):
        owner = context[0]
        manifest = store.manifest(owner, body.manifest_id)
        previous = store.replay(owner, body, manifest, idempotency_key)
        if previous is not None:
            return public_task(previous)
        if not manifest["complete"]:
            raise HubError("incomplete", "未完成的清单不能提交下载", 409)
        songs = [e["song"] for e in manifest["ordered_entries"]]
        if manifest["source"]["kind"] == "remote_playlist" or any(
            not s["track"] or s["track"]["provider"] != "kuwo" for s in songs
        ):
            raise HubError(
                "unsupported", "此开发版先验证酷我链路，QQ/网易账号下载尚未开放", 409
            )
        if any(
            s["duration_seconds"] <= 0
            or body.quality not in {q["quality"] for q in s["qualities"]}
            for s in songs
        ):
            raise HubError(
                "unavailable",
                "部分曲目缺少完整时长或所选音质，仍可保留在搜索与收藏中",
                409,
            )
        await engines.check_target(owner)
        store.check_session(context[1])
        task, created = store.submit(
            owner, body, manifest, idempotency_key, engines.runtime_key(owner)
        )
        response.status_code = 202 if created else 200
        return public_task(task)

    @app.get("/api/tasks")
    async def tasks(context=Depends(authenticated)):
        return {
            "items": [public_task(t) for t in store.owned_list("tasks", context[0])]
        }

    @app.post("/api/tasks/{task_id}/control")
    async def control(task_id: str, body: ControlInput, context=Depends(authenticated)):
        task = await reconciler.control(
            context[0],
            task_id,
            body.action,
            lambda: store.check_session(context[1]),
        )
        store.check_session(context[1])
        return public_task(task)

    @app.get("/api/assets")
    async def assets(context=Depends(authenticated)):
        return {
            "items": [public_asset(a) for a in store.owned_list("assets", context[0])]
        }

    @app.get("/api/assets/{asset_id}/file")
    async def file(asset_id: str, context=Depends(authenticated)):
        owner = context[0]
        asset = store._owned("assets", owner.key, asset_id)
        if asset["runtime_key"] != engines.runtime_key(owner):
            raise HubError("forbidden", "该文件的授权目录配置已变化", 403)
        fd = open_asset(engines.config(owner).download_root, asset)
        stream = os.fdopen(fd, "rb")

        def chunks():
            try:
                while chunk := stream.read(256 * 1024):
                    yield chunk
            finally:
                stream.close()

        ext = "flac" if asset["codec"] == "flac" else "mp3"
        return StreamingResponse(
            chunks(),
            media_type="audio/flac" if ext == "flac" else "audio/mpeg",
            headers={
                "Content-Length": str(asset["bytes"]),
                "Content-Disposition": f'attachment; filename="{asset_id}.{ext}"',
            },
            background=BackgroundTask(stream.close),
        )

    @app.get("/api/admin/injection")
    async def injection(context=Depends(authenticated)):
        if context[0].user_guid not in settings.admin_guids:
            raise HubError("forbidden", "只有管理员可以查看注入设置", 403)
        return {
            "enabled": False,
            "available": False,
            "socket_owner": "unchanged",
            "reason": "此开发版未接管官方音乐 Socket；独立登录、歌单和下载不依赖注入",
        }

    web = Path(__file__).resolve().parents[1] / "apps" / "web"
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    async def index():
        return FileResponse(web / "index.html")

    return app
