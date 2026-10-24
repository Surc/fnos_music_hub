"""Explicit NetEase consent and frozen, encrypted per-owner Cookie grants."""

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from uuid import uuid4

from cryptography.fernet import InvalidToken

from hub.account_store import AccountStore
from hub.domain import canonical, digest
from hub.errors import HubError


def parse_cookie(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 16384
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise HubError("invalid_request", "网易 Cookie 格式不合法")
    jar = SimpleCookie()
    try:
        jar.load(value)
    except CookieError:
        raise HubError("invalid_request", "网易 Cookie 格式不合法") from None
    # Only protocol credentials, never headers, domains, paths or arbitrary cookie attributes.
    allowed = {"MUSIC_U", "__csrf", "NMTID", "deviceId"}
    cookies = {k: v.value for k, v in jar.items() if k in allowed}
    if not cookies.get("MUSIC_U") or any(
        not re.fullmatch(r"[A-Za-z0-9_./+=%~-]{1,8192}", v) for v in cookies.values()
    ):
        raise HubError("invalid_request", "需要有效的 MUSIC_U 登录 Cookie")
    return canonical(cookies)


@dataclass(frozen=True, repr=False)
class NeteaseCredential:
    cookies: str
    uid: str | None = None

    @property
    def fingerprint(self):
        return digest({"cookies": self.cookies, "uid": self.uid})


class NeteaseAccounts:
    def __init__(self, settings, store, protocol):
        self.settings, self.store, self.protocol = (
            settings,
            AccountStore(store, "netease"),
            protocol,
        )
        self.locks = defaultdict(asyncio.Lock)

    def enabled(self, owner):
        return self.settings.netease_enabled

    def require(self, owner):
        if not self.enabled(owner):
            raise HubError("unsupported", "管理员尚未启用网易只读目录", 409)

    @staticmethod
    def public(account):
        return {
            k: account.get(k)
            for k in (
                "provider",
                "state",
                "binding_generation",
                "credential_revision",
                "account_ref",
                "uid",
                "nickname",
            )
        }

    def purge(self, owner):
        # Explicit local favorites are independent and survive unlink; transient metadata does not.
        with self.store.store.db() as db:
            db.execute(
                "DELETE FROM songs WHERE owner=? AND json_extract(payload, '$.track.provider')='netease'",
                (owner.key,),
            )

    async def status(self, owner, session):
        if not self.enabled(owner):
            return {"enabled": False, "items": []}
        self.store.store.check_session(session)
        return {"enabled": True, "items": [self.public(self.store.get(owner))]}

    async def start(self, owner, session, cookie):
        self.require(owner)
        credential = NeteaseCredential(parse_cookie(cookie))
        async with self.locks[owner.key]:
            attempt = self.store.begin(owner, session, "netease-readonly-v1", "cookie")
        try:
            profile = await self.protocol.read(credential, "verify")
            async with self.locks[owner.key]:
                attempt, _ = self.store.current_attempt(owner, session, attempt["id"])
                attempt.update(
                    status="confirmed",
                    uid=profile["uid"],
                    nickname=profile["nickname"],
                    cookies=credential.cookies,
                )
                self.store.save_attempt(owner, session, attempt)
        except BaseException:
            async with self.locks[owner.key]:
                current = self.store.get(owner)
                if current.get("attempt_id") == attempt["id"]:
                    self.store.replace(
                        owner,
                        current,
                        {**current, "attempt_id": None, "attempt_expires": 0},
                    )
                with self.store.store.db() as db:
                    db.execute(
                        "DELETE FROM account_attempts WHERE id=? AND owner=?",
                        (attempt["id"], owner.key),
                    )
            raise
        return {k: attempt[k] for k in ("id", "status", "uid", "nickname", "expires")}

    async def bind(self, owner, session, attempt_id):
        self.require(owner)
        async with self.locks[owner.key]:
            attempt, old = self.store.current_attempt(owner, session, attempt_id)
            if attempt["status"] == "bound" and old["state"] == "bound":
                return self.public(old)
            if attempt["status"] != "confirmed":
                raise HubError("conflict", "请先验证并核对网易账号", 409)
            snapshot = NeteaseCredential(attempt["cookies"], attempt["uid"])
        await self.protocol.read(snapshot, "verify")
        async with self.locks[owner.key]:
            attempt, current = self.store.current_attempt(owner, session, attempt_id)
            if current != old:
                raise HubError("binding_changed", "验证期间账号已变化", 409)
            attempt.pop("cookies", None)
            attempt["status"] = "bound"
            bound = self.store.replace(
                owner,
                old,
                {
                    **old,
                    "state": "bound",
                    "uid": snapshot.uid,
                    "nickname": attempt["nickname"],
                    "account_ref": uuid4().hex,
                    "credential_revision": 1,
                    "attempt_expires": 0,
                    "credential": self.store.store.vault.encrypt(
                        snapshot.cookies.encode()
                    ).decode(),
                },
                session=session,
                attempt=attempt,
            )
            return self.public(bound)

    async def unlink(self, owner, session, generation):
        self.require(owner)
        async with self.locks[owner.key]:
            self.store.store.check_session(session)
            old = self.store.get(owner)
            if old["binding_generation"] != generation:
                raise HubError("conflict", "账号代次已变化，请刷新后操作", 409)
            value = self.store.replace(
                owner,
                old,
                {
                    "provider": "netease",
                    "state": "unbound",
                    "binding_generation": generation + 1,
                    "credential_revision": 0,
                    "account_ref": None,
                    "uid": None,
                    "nickname": None,
                },
            )
            with self.store.store.db() as db:
                db.execute(
                    "DELETE FROM account_attempts WHERE owner=? AND id=?",
                    (owner.key, old.get("attempt_id")),
                )
            self.purge(owner)
            return self.public(value)

    async def rotate(self, owner, session, generation, cookie):
        self.require(owner)
        async with self.locks[owner.key]:
            self.store.store.check_session(session)
            old = self.store.get(owner)
            if (
                old["state"] not in {"bound", "expired"}
                or old["binding_generation"] != generation
            ):
                raise HubError("conflict", "请刷新账号状态后更新凭据", 409)
            snapshot = NeteaseCredential(parse_cookie(cookie), old["uid"])
        await self.protocol.read(snapshot, "verify")
        async with self.locks[owner.key]:
            self.store.store.check_session(session)
            value = self.store.replace(
                owner,
                old,
                {
                    **old,
                    "state": "bound",
                    "credential_revision": old["credential_revision"] + 1,
                    "credential": self.store.store.vault.encrypt(
                        snapshot.cookies.encode()
                    ).decode(),
                },
            )
            self.purge(owner)
            return self.public(value)

    async def snapshot(self, owner, session):
        self.require(owner)
        async with self.locks[owner.key]:
            self.store.store.check_session(session)
            account = self.store.get(owner)
            if account["state"] != "bound":
                raise HubError(
                    "platform_auth_required",
                    "请关联有效的本人网易账号；不会回退公共内容",
                    409,
                )
            try:
                cookies = self.store.store.vault.decrypt(
                    account["credential"].encode()
                ).decode()
            except (InvalidToken, KeyError, ValueError):
                raise HubError(
                    "platform_auth_required", "网易凭据无法读取，请重新关联", 409
                ) from None
            return self.public(account), NeteaseCredential(cookies, account["uid"])

    async def validate(self, owner, session, grant, snapshot):
        self.store.store.check_session(session)
        current = self.store.get(owner)
        if self.public(current) != grant or current.get("credential") is None:
            raise HubError(
                "binding_changed", "请求期间网易账号或凭据已变化，请重新加载", 409
            )

    async def expired(self, owner, session, grant):
        async with self.locks[owner.key]:
            self.store.store.check_session(session)
            current = self.store.get(owner)
            if self.public(current) == grant:
                self.store.replace(owner, current, {**current, "state": "expired"})
                self.purge(owner)
