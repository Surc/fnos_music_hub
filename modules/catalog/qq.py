"""QQMusicApi is the sole QQ recommendation/list protocol. No refresh calls."""

import asyncio
import importlib.util
from dataclasses import replace

from hub.domain import TrackRef
from hub.errors import HubError

SDK_COMMIT = "27861e51432ea6b6e88dc35c4e8c8e239c0339e8"


def unknown(position):
    return {
        "track": None,
        "title": "来源中的未知条目",
        "artist": "",
        "album": "",
        "duration_seconds": 0,
        "qualities": [],
        "availability": "unknown",
        "source_position": position,
    }


def song_metadata(raw, position):
    try:
        mid = raw.get("mid")
        track = TrackRef(
            provider="qq",
            id_type="songmid" if mid else "songid",
            id=mid if mid else str(raw["id"]),
        )
        singers = raw.get("singer", [])
        album = raw.get("album") or {}
        return {
            "track": track.model_dump(),
            "title": str(raw.get("title") or raw.get("name") or "")[:512],
            "artist": " / ".join(str(s.get("name", "")) for s in singers)[:512],
            "album": str(album.get("name", ""))[:512],
            "duration_seconds": max(0, int(raw.get("interval", 0))),
            "qualities": [],
            "availability": "unverified",
            "source_position": position,
        }
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return unknown(position)


def playlist_metadata(raw, position):
    try:
        if not isinstance(raw, dict):
            raise ValueError()
        pid = str(raw.get("tid", raw.get("id", raw.get("dissid", ""))))
        dirid = str(raw.get("dirid", raw.get("dirId", 0)))
        if (
            not pid.isascii()
            or not pid.isdecimal()
            or not dirid.isascii()
            or not dirid.isdecimal()
        ):
            raise ValueError()
        creator = raw.get("creator") or {}
        return {
            "playlist": {"provider": "qq", "id": pid, "dirid": dirid},
            "title": str(
                raw.get("title") or raw.get("dirName") or raw.get("name") or ""
            )[:512],
            "creator": str(creator.get("nick", raw.get("nick", "")))[:512],
            "song_count": max(
                0, int(raw.get("song_cnt", raw.get("songNum", raw.get("songnum", 0))))
            ),
            "source_position": position,
        }
    except (ValueError, TypeError, AttributeError):
        return {
            "playlist": None,
            "title": "来源中的未知歌单",
            "source_position": position,
        }


class QqProtocol:
    """A fresh SDK Client receives only this request's immutable credential value."""

    @staticmethod
    def available():
        return importlib.util.find_spec("qqmusic_api") is not None

    async def read(
        self, snapshot, operation, *, page=1, cursor=0, playlist_id=None, dirid=None
    ):
        try:
            from qqmusic_api import Client, Credential, __version__
            from qqmusic_api.core.exceptions import (
                CredentialExpiredError,
                CredentialInvalidError,
                LoginAuthExpiredError,
                NetworkError,
                RatelimitedError,
            )
        except ImportError:
            raise HubError("unsupported", "固定版本 QQ SDK 尚未安装", 503) from None
        try:
            if __version__ != "0.8.2":
                raise HubError("upstream_contract", "QQ SDK 版本与固定接口不匹配", 503)
            credential = Credential.model_validate(snapshot.credential())
            if not credential.is_valid():
                raise HubError(
                    "platform_auth_required", "QQ 登录凭据不完整，请重新扫码", 409
                )
            # No global SDK credential, credential pool, filesystem device cache or refresh owner.
            async with (
                asyncio.timeout(30),
                Client(credential=credential, max_concurrency=2) as client,
            ):
                if await client.login.check_expired(credential):
                    raise HubError(
                        "platform_auth_required", "QQ 登录已过期，请重新扫码", 409
                    )
                if operation == "verify":
                    return {}
                if operation == "recommend_playlists":
                    request = client.recommend.get_recommend_songlist(page=page, num=20)
                    request = replace(request, param={**request.param, "From": cursor})
                elif operation == "recommend_songs":
                    request = client.recommend.get_guess_recommend(
                        credential=credential
                    )
                elif operation == "created_playlists":
                    request = client.user.get_created_songlist(
                        int(snapshot.uin), credential=credential
                    )
                elif operation == "playlist_page":
                    request = client.songlist.get_detail(
                        int(playlist_id), dirid=int(dirid), num=100, page=page
                    )
                else:
                    raise HubError("unsupported", "未支持的 QQ 只读操作", 409)
                # Use upstream request construction/signing/error handling, but retain raw entries.
                # Typed Song lists otherwise reject a whole page containing one unknown entry.
                result = await client.execute(
                    replace(
                        request,
                        response_model=None,
                        require_login=True,
                        credential=credential,
                    )
                )
                if not isinstance(result, dict):
                    raise HubError("upstream_contract", "QQ 目录响应格式不匹配", 502)
                return result
        except HubError:
            raise
        except (CredentialExpiredError, CredentialInvalidError, LoginAuthExpiredError):
            raise HubError(
                "platform_auth_required", "QQ 登录已失效，请重新扫码", 409
            ) from None
        except RatelimitedError:
            raise HubError("rate_limited", "QQ 暂时限制请求，请稍后再试", 429) from None
        except (NetworkError, TimeoutError):
            raise HubError(
                "platform_unavailable", "QQ 暂未返回可确认结果，请稍后再试", 503
            ) from None
        except Exception:
            # SDK exceptions may contain credentials/raw responses. Never expose or log them.
            raise HubError(
                "upstream_contract", "QQ 只读接口未返回符合约定的结果", 502
            ) from None


class QqCatalog:
    def __init__(self, accounts, protocol, store):
        self.accounts, self.protocol, self.store = accounts, protocol, store

    async def read(self, owner, operation, **kwargs):
        grant, snapshot = await self.accounts.snapshot(owner)
        return await self.read_bound(owner, grant, snapshot, operation, **kwargs), grant

    async def read_bound(self, owner, grant, snapshot, operation, **kwargs):
        # Full captures reuse one frozen grant across every page and both passes.
        await self.accounts.validate(owner, grant, snapshot)
        try:
            result = await self.protocol.read(snapshot, operation, **kwargs)
        except HubError as exc:
            if exc.code == "platform_auth_required":
                await self.accounts.expired(owner, grant, snapshot)
            raise
        # Recheck binding, runtime and credential revision after every awaited platform request.
        await self.accounts.validate(owner, grant, snapshot)
        return result

    def songs(self, owner, rows, start=0):
        if not isinstance(rows, list) or len(rows) > 1000:
            raise HubError("upstream_contract", "QQ 曲目页结构或容量不匹配", 502)
        songs = [song_metadata(raw, i) for i, raw in enumerate(rows, start)]
        for song in songs:
            if song["track"]:
                self.store.cache_song(owner, song)
        return songs

    async def recommendations(self, owner, kind, page, cursor=0):
        operation = "recommend_playlists" if kind == "playlists" else "recommend_songs"
        result, grant = await self.read(owner, operation, page=page, cursor=cursor)
        if kind == "playlists":
            rows = result.get("List")
            if not isinstance(rows, list) or len(rows) > 100:
                raise HubError("upstream_contract", "QQ 推荐歌单结构不匹配", 502)
            items = [
                playlist_metadata(
                    raw["Playlist"].get("basic")
                    if isinstance(raw, dict) and isinstance(raw.get("Playlist"), dict)
                    else None,
                    i,
                )
                for i, raw in enumerate(rows)
            ]
            more = (
                result.get("HasMore") is True
                or type(result.get("HasMore")) is int
                and result["HasMore"] == 1
            )
            next_cursor = result.get("FromLimit") if more else None
            if more and (
                type(next_cursor) is not int or not cursor < next_cursor <= 100000
            ):
                raise HubError("upstream_contract", "QQ 推荐缺少有效的继续游标", 502)
        else:
            items, more = self.songs(owner, result.get("tracks")), False
            next_cursor = None
        return {
            "items": items,
            "kind": "recommended_playlists" if kind == "playlists" else "guess_songs",
            "provider": "qq",
            "scope": "account",
            "personalization": "unverified",
            "page": page,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": more,
            "account": grant,
        }

    async def playlists(self, owner):
        result, grant = await self.read(owner, "created_playlists")
        rows = result.get("v_playlist")
        if not isinstance(rows, list) or len(rows) > 1000:
            raise HubError("upstream_contract", "QQ 本人歌单结构不匹配", 502)
        return {
            "items": [playlist_metadata(raw, i) for i, raw in enumerate(rows)],
            "kind": "created_playlists",
            "scope": "account",
            "provider": "qq",
            "account": grant,
            "complete": result.get("bFinish") is True
            and result.get("total") == len(rows),
        }

    async def playlist_page(self, owner, playlist_id, dirid, page):
        result, grant = await self.read(
            owner, "playlist_page", playlist_id=playlist_id, dirid=dirid, page=page
        )
        items = self.songs(owner, result.get("songlist"), (page - 1) * 100)
        total = result.get("total_song_num")
        if type(total) is not int or total < 0:
            raise HubError("upstream_contract", "QQ 歌单缺少可信总数", 502)
        return {
            "items": items,
            "playlist": playlist_metadata(result.get("dirinfo"), 0),
            "source_total": total,
            "page": page,
            "page_size": 100,
            "has_more": bool(result.get("hasmore")),
            "complete": False,
            "integrity": "page_only",
            "provider": "qq",
            "scope": "account",
            "account": grant,
        }
