"""NetEase metadata only. No link resolution, cloud writes or download admission."""

import asyncio
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path

from hub.domain import TrackRef, canonical
from hub.errors import HubError
from modules.accounts.netease import NeteaseCredential
from modules.catalog.qq import unknown

SDK_COMMIT = "9c405f4bae2384d0410e63f8b816a707553d72d3"
PAGE_SIZE = 30
TRACK_PAGE_SIZE = 100


class NeteaseProtocol:
    def __init__(self):
        self.slots = asyncio.Semaphore(4)

    @staticmethod
    def available():
        try:
            return importlib.metadata.version("NetEase-MusicBox") == "0.5.3"
        except importlib.metadata.PackageNotFoundError:
            return False

    async def read(self, snapshot, operation, **kwargs):
        if not self.available():
            raise HubError("unsupported", "固定版网易目录依赖尚未安装", 503)
        # NEMbox imports create XDG files and use singletons. Never import it in the Hub.
        # Short-lived workers have private XDG directories, memory-only HTTP cookies/cache.
        async with self.slots:
            with tempfile.TemporaryDirectory(prefix="hub-netease-") as directory:
                env = {
                    k: v
                    for k, v in os.environ.items()
                    if k.upper()
                    not in {
                        "HTTP_PROXY",
                        "HTTPS_PROXY",
                        "ALL_PROXY",
                        "NO_PROXY",
                    }
                }
                for key in (
                    "XDG_CONFIG_HOME",
                    "XDG_CACHE_HOME",
                    "XDG_DATA_HOME",
                    "XDG_RUNTIME_DIR",
                ):
                    path = Path(directory) / key.lower()
                    path.mkdir(mode=0o700)
                    env[key] = str(path)
                process = None
                try:
                    async with asyncio.timeout(45):
                        process = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "modules.catalog.netease_worker",
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.DEVNULL,
                            env=env,
                        )
                        payload = canonical(
                            {
                                "cookies": json.loads(snapshot.cookies),
                                "uid": snapshot.uid,
                                "operation": operation,
                                **kwargs,
                            }
                        ).encode()
                        process.stdin.write(payload)
                        await process.stdin.drain()
                        process.stdin.close()
                        chunks, size = [], 0
                        while chunk := await process.stdout.read(65536):
                            size += len(chunk)
                            if size > 2 * 1024 * 1024:
                                raise HubError(
                                    "capacity_exceeded", "网易目录响应超过容量限制", 413
                                )
                            chunks.append(chunk)
                        await process.wait()
                        result = json.loads(b"".join(chunks))
                        if "error" in result:
                            code = result["error"]
                            errors = {
                                "platform_auth_required": (
                                    "网易登录已失效，请更新凭据",
                                    409,
                                ),
                                "binding_changed": (
                                    "网易账号已变化，请先解除关联后换号",
                                    409,
                                ),
                                "rate_limited": ("网易暂时限制请求，请稍后再试", 429),
                                "incomplete": ("来源歌单目录被截断，无法可靠翻页", 409),
                                "platform_unavailable": (
                                    "网易暂时不可用，请稍后再试",
                                    503,
                                ),
                            }
                            message, status = errors.get(
                                code, ("网易目录响应不符合约定", 502)
                            )
                            raise HubError(
                                code if code in errors else "upstream_contract",
                                message,
                                status,
                            )
                        if process.returncode or not isinstance(
                            result.get("data"), dict
                        ):
                            raise ValueError()
                        return result["data"]
                except (TimeoutError, OSError):
                    raise HubError(
                        "platform_unavailable", "网易读取超时或暂不可用", 503
                    ) from None
                except (ValueError, TypeError, KeyError):
                    raise HubError(
                        "upstream_contract", "网易目录进程未返回可靠结果", 502
                    ) from None
                finally:
                    if process is not None and process.returncode is None:
                        process.kill()
                        await process.wait()


def song_metadata(raw, position):
    try:
        track = TrackRef(provider="netease", id_type="songid", id=str(raw["id"]))
        artists, album = (
            raw.get("ar", raw.get("artists", [])),
            raw.get("al", raw.get("album", {})),
        )
        return {
            "track": track.model_dump(),
            "title": str(raw.get("name", ""))[:512],
            "artist": " / ".join(str(a.get("name", "")) for a in artists)[:512],
            "album": str(album.get("name", ""))[:512],
            "duration_seconds": max(
                0, int(raw.get("dt", raw.get("duration", 0))) // 1000
            ),
            "qualities": [],
            "availability": "unverified",
            "source_position": position,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return unknown(position)


def playlist_metadata(raw, position):
    try:
        pid = str(raw["id"])
        if not pid.isascii() or not pid.isdecimal() or int(pid) <= 0:
            raise ValueError()
        return {
            "playlist": {"provider": "netease", "id": pid},
            "title": str(raw.get("name", ""))[:512],
            "creator": str((raw.get("creator") or {}).get("nickname", ""))[:512],
            "song_count": max(0, int(raw.get("trackCount", 0))),
            "source_position": position,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return {
            "playlist": None,
            "title": "来源中的未知歌单",
            "source_position": position,
        }


class NeteaseCatalog:
    def __init__(self, accounts, protocol, store):
        self.accounts, self.protocol, self.store = accounts, protocol, store

    async def read(self, owner, session, operation, scope, **kwargs):
        self.accounts.require(owner)
        self.store.check_session(session)
        grant, snapshot = (None, NeteaseCredential("{}"))
        if scope == "account":
            grant, snapshot = await self.accounts.snapshot(owner, session)
        try:
            data = await self.protocol.read(snapshot, operation, **kwargs)
        except HubError as exc:
            if grant:
                await self.accounts.validate(owner, session, grant, snapshot)
                if exc.code in {"platform_auth_required", "binding_changed"}:
                    await self.accounts.expired(owner, session, grant)
            raise
        self.store.check_session(session)
        if grant:
            await self.accounts.validate(owner, session, grant, snapshot)
        return data, grant

    async def page(self, owner, session, operation, scope, page, playlist_id=None):
        data, grant = await self.read(
            owner, session, operation, scope, page=page, playlist_id=playlist_id
        )
        rows, more = data.get("items"), data.get("has_more")
        size = TRACK_PAGE_SIZE if operation == "playlist_page" else PAGE_SIZE
        if not isinstance(rows, list) or len(rows) > size or type(more) is not bool:
            raise HubError("upstream_contract", "网易分页结构不可靠", 502)
        if operation == "playlist_page":
            total = data.get("source_total")
            if type(total) is not int or total < 0 or total > 10000:
                raise HubError("upstream_contract", "网易歌单缺少可信总数", 502)
            expected = max(0, min(size, total - (page - 1) * size))
            if len(rows) != expected or more != (page * size < total):
                raise HubError("incomplete", "网易歌单页长度与来源总数不一致", 409)
        is_songs = operation in {"playlist_page", "recommend_songs"}
        items = [
            (song_metadata if is_songs else playlist_metadata)(
                row, (page - 1) * size + i
            )
            for i, row in enumerate(rows)
        ]
        for song in items if is_songs else []:
            if song["track"]:
                self.store.cache_song(owner, song)
        result = {
            "provider": "netease",
            "scope": scope,
            "account": grant,
            "items": items,
            "kind": operation,
            "page": page,
            "page_size": size,
            "has_more": more,
            "complete": False,
            "integrity": "page_only",
            "personalization": "unverified",
        }
        if operation == "playlist_page":
            result.update(
                source_total=total, playlist=playlist_metadata(data.get("playlist"), 0)
            )
        return result
