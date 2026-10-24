"""One-shot MusicBox adapter. Stdin credentials; sanitized stdout; no durable SDK state."""

import contextlib
import json
import logging
import os
import sys

from hub.errors import HubError


def execute(payload):
    import requests
    from NEMbox.api import NetEase

    def checked(data):
        if not isinstance(data, dict):
            raise HubError("upstream_contract", "", 502)
        code = data.get("code")
        if code in {301, 302, 401}:
            raise HubError("platform_auth_required", "", 409)
        if code in {405, 429}:
            raise HubError("rate_limited", "", 429)
        if code != 200:
            raise HubError("upstream_contract", "", 502)
        return data

    class Session(requests.Session):
        def request(self, method, url, **kwargs):
            try:
                return self.bounded_request(method, url, **kwargs)
            except requests.RequestException:
                # Raise outside the SDK's swallowed RequestException/default-empty path.
                raise HubError("platform_unavailable", "", 503) from None

        def bounded_request(self, method, url, **kwargs):
            if not url.startswith(
                ("https://music.163.com/", "https://interface.music.163.com/")
            ):
                raise HubError("upstream_contract", "", 502)
            kwargs.update(allow_redirects=False, stream=True)
            response = super().request(method, url, **kwargs)
            with response:
                if response.status_code == 401:
                    raise HubError("platform_auth_required", "", 409)
                if response.status_code == 429:
                    raise HubError("rate_limited", "", 429)
                if response.status_code >= 500:
                    raise HubError("platform_unavailable", "", 503)
                if response.status_code != 200:
                    raise HubError("upstream_contract", "", 502)
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise HubError("incomplete", "", 409)
                    chunks.append(chunk)
                response._content = b"".join(chunks)
            return response

    class Api(NetEase):
        def __init__(self):
            # Bypass NetEase's global Storage/Config/CachedSession initialization.
            self.session = Session()
            self.session.trust_env = False
            self.header = {
                "Referer": "https://music.163.com",
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            self._device_id = (
                payload["cookies"].get("deviceId") or self._gen_device_id()
            )
            for name, value in payload["cookies"].items():
                self.session.cookies.set_cookie(self.make_cookie(name, value))

        def request(self, *args, **kwargs):
            self.last = checked(super().request(*args, **kwargs))
            return self.last

        def eapi_request(self, *args, **kwargs):
            self.last = checked(super().eapi_request(*args, **kwargs))
            return self.last

        def _persist_new_nmtid(self, had_nmtid):
            pass  # No persistent cookie writer or refresh owner in the catalog adapter.

    api = Api()
    try:

        def identity():
            data = api.get_account_info()
            account, profile = data.get("account") or {}, data.get("profile") or {}
            uid, profile_uid = account.get("id"), profile.get("userId")
            uid = uid if uid is not None else profile_uid
            if (
                type(uid) is not int
                or uid <= 0
                or profile_uid is not None
                and type(profile_uid) is not int
                or profile_uid is not None
                and profile_uid != uid
            ):
                raise HubError("platform_auth_required", "", 409)
            if payload.get("uid") and str(uid) != payload["uid"]:
                raise HubError("binding_changed", "", 409)
            return {"uid": str(uid), "nickname": str(profile.get("nickname", ""))[:128]}

        operation, page = payload["operation"], payload.get("page", 1)
        private = bool(payload["cookies"])
        profile = identity() if private else None
        if operation == "verify":
            if not profile:
                raise HubError("platform_auth_required", "", 409)
            return profile
        offset = (page - 1) * 30
        if operation in {"public_playlists", "user_playlists"}:
            if operation == "public_playlists":
                rows = api.top_playlists(offset=offset, limit=30)
            elif profile:
                rows = api.user_playlist(int(profile["uid"]), offset=offset, limit=30)
            else:
                raise HubError("platform_auth_required", "", 409)
            more = api.last.get("more")
            field = "playlists" if operation == "public_playlists" else "playlist"
            if type(more) is not bool or not isinstance(api.last.get(field), list):
                raise HubError("upstream_contract", "", 502)
            result = {"items": rows, "has_more": more}
        elif operation in {"recommend_playlists", "recommend_songs"} and profile:
            rows = (
                api.recommend_resource()
                if operation == "recommend_playlists"
                else api.recommend_playlist(limit=0)
            )
            raw = api.last.get("recommend")
            if raw is None and operation == "recommend_songs":
                raw = (api.last.get("data") or {}).get("dailySongs")
            if not isinstance(raw, list):
                raise HubError("upstream_contract", "", 502)
            if not isinstance(rows, list) or len(rows) > 1000:
                raise HubError("upstream_contract", "", 502)
            result = {
                "items": rows[offset : offset + 30],
                "has_more": offset + 30 < len(rows),
            }
        elif operation == "playlist_page":
            ids = api.playlist_songlist(int(payload["playlist_id"]))
            playlist = api.last.get("playlist")
            if (
                not isinstance(playlist, dict)
                or str(playlist.get("id")) != payload["playlist_id"]
            ):
                raise HubError("upstream_contract", "", 502)
            total = playlist.get("trackCount")
            if (
                not isinstance(ids, list)
                or type(total) is not int
                or not isinstance(playlist.get("trackIds"), list)
                or total != len(ids)
                or total > 10000
            ):
                raise HubError("incomplete", "", 409)
            selected = ids[(page - 1) * 100 : page * 100]
            valid = [
                r["id"]
                for r in selected
                if isinstance(r, dict) and type(r.get("id")) is int and r["id"] > 0
            ]
            # Deduplicate detail requests only; reconstruct every source occurrence below.
            rows = api.songs_detail(list(dict.fromkeys(valid))) if valid else []
            if (
                not isinstance(rows, list)
                or valid
                and not isinstance(api.last.get("songs"), list)
            ):
                raise HubError("upstream_contract", "", 502)
            mapping = {
                r["id"]: r
                for r in rows
                if isinstance(r, dict) and type(r.get("id")) is int and r["id"] in valid
            }
            result = {
                "items": [
                    mapping.get(r.get("id")) if isinstance(r, dict) else None
                    for r in selected
                ],
                "playlist": {
                    key: playlist.get(key)
                    for key in ("id", "name", "trackCount", "creator")
                },
                "source_total": total,
                "has_more": page * 100 < total,
            }
        else:
            raise HubError("upstream_contract", "", 502)
        if private:
            identity()
        return result
    except requests.RequestException:
        raise HubError("platform_unavailable", "", 503) from None
    finally:
        api.session.close()


def main():
    # Never let upstream diagnostics leak cookies/raw pages to either output channel.
    logging.disable(logging.CRITICAL)
    try:
        payload = json.loads(sys.stdin.buffer.read(32769))
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            data = execute(payload)
        output = {"data": data}
    except HubError as exc:
        output = {"error": exc.code}
    except Exception:
        output = {"error": "upstream_contract"}
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
