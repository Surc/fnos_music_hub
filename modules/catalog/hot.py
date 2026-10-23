"""Hot's public search is metadata-only; no stream/link probe is performed here."""

from hub.domain import TrackRef
from hub.errors import HubError


def normalize_song(raw, provider="kuwo"):
    if not isinstance(raw, dict):
        raise ValueError("song is not an object")
    platform = "kuwo" if provider == "kuwo" else "qqmusic"
    if raw.get("platform", platform) != platform:
        raise ValueError("platform mismatch")
    mid = raw.get("mid", "")
    track = TrackRef(
        provider=provider,
        id_type="rid" if provider == "kuwo" else "songmid" if mid else "songid",
        id=str(raw["id"]) if provider == "kuwo" or not mid else mid,
    )
    qualities = []
    for item in raw.get("qualities", []):
        if isinstance(item, dict) and isinstance(item.get("quality"), str):
            filename = item.get("filename", "")
            if not isinstance(filename, str) or any(
                c in filename for c in ("/", "\\", "\x00")
            ):
                raise ValueError("unsafe quality filename")
            qualities.append(
                {
                    "quality": item["quality"],
                    "filename": filename,
                    "size": max(0, int(item.get("size", 0))),
                }
            )
    return {
        "track": track.model_dump(),
        "title": str(raw.get("title", ""))[:512],
        "artist": str(raw.get("artist", ""))[:512],
        "album": str(raw.get("album", ""))[:512],
        "duration_seconds": max(0, float(raw.get("duration") or 0)),
        "qualities": qualities,
        "availability": "unverified",
        # Numeric IDs remain strings in Hub. Conversion is only at this adapter boundary.
        "engine_song": {
            "platform": platform,
            "id": int(raw["id"]),
            "mid": str(raw.get("mid", "")),
            "title": str(raw.get("title", ""))[:512],
            "artist": str(raw.get("artist", ""))[:512],
            "album": str(raw.get("album", ""))[:512],
            "coverUrl": "",
            "mediaMid": str(raw.get("mediaMid", "")),
            "qualities": qualities,
        },
    }


def public_song(song):
    return {key: value for key, value in song.items() if key != "engine_song"}


class HotCatalog:
    def __init__(self, engines, store):
        self.engines, self.store = engines, store

    async def search(self, owner, provider, keyword, page=1, *, session=None):
        if session is not None:
            self.store.check_session(session)
        if provider not in {"kuwo", "qq"}:
            raise HubError("unsupported", "网易目录适配尚未接入", 409)
        result = await self.engines.call(
            owner,
            "POST",
            "/api/music/songs/search",
            {
                "platform": "kuwo" if provider == "kuwo" else "qqmusic",
                "keyword": keyword,
                "page": page,
                "limit": 30,
            },
        )
        if session is not None:
            self.store.check_session(session)
        if not isinstance(result, dict) or not isinstance(result.get("songs"), list):
            raise HubError("upstream_contract", "下载引擎返回了未知搜索结构", 502)
        items = []
        for i, raw in enumerate(result["songs"]):
            try:
                song = normalize_song(raw, provider)
                self.store.cache_song(owner, song)
                items.append(public_song(song))
            except (ValueError, KeyError, TypeError, OverflowError):
                # Keep a visible placeholder instead of silently shortening the source list.
                items.append(
                    {
                        "track": None,
                        "title": "来源中的未知条目",
                        "artist": "",
                        "availability": "unknown",
                        "source_position": i,
                        "qualities": [],
                    }
                )
        return {
            "items": items,
            "has_more": result.get("has_more") is True,
            "page": page,
            "kind": "search",
            "provider": provider,
        }
