"""QQ binding facade: explicit consent, session attempts, revocable read grants."""

import asyncio
import base64
import binascii
import re
from collections import defaultdict
from uuid import uuid4

from .account_store import AccountStore
from .errors import HubError


class Accounts:
    def __init__(self, settings, store, native, protocol):
        self.settings, self.store, self.native, self.protocol = (
            settings,
            AccountStore(store),
            native,
            protocol,
        )
        self.locks = defaultdict(asyncio.Lock)

    def enabled(self, owner):
        return (
            self.settings.qq_accounts_enabled and owner.user_guid in self.settings.users
        )

    def require(self, owner):
        if not self.enabled(owner):
            raise HubError("unsupported", "管理员尚未为此用户启用 QQ 账号模块", 409)

    @staticmethod
    def public(account):
        return {
            key: account.get(key)
            for key in (
                "provider",
                "state",
                "binding_generation",
                "credential_revision",
                "account_ref",
                "uin",
            )
        }

    def observe(self, owner):
        account = self.store.get(owner)
        if account["state"] not in {"bound", "expired"}:
            return account, None
        snapshot = self.native.read(owner)
        if (
            snapshot is None
            or snapshot.uin != account["uin"]
            or account.get("runtime_key") != self.native.engines.runtime_key(owner)
        ):
            return self.store.replace(
                owner,
                account,
                {
                    **account,
                    "state": "binding_changed",
                    "binding_generation": account["binding_generation"] + 1,
                    "credential_revision": 0,
                    "account_ref": None,
                    "uin": None,
                    "attempt_id": None,
                    "attempt_expires": 0,
                    "fingerprint": None,
                },
            ), None
        if snapshot.fingerprint != account.get("fingerprint"):
            account = self.store.replace(
                owner,
                account,
                {
                    **account,
                    "fingerprint": snapshot.fingerprint,
                    "credential_revision": account["credential_revision"] + 1,
                    "state": "bound",
                },
            )
        return account, snapshot

    async def status(self, owner):
        if not self.enabled(owner):
            return {"items": [], "enabled": False}
        async with self.locks[owner.key]:
            account, _ = self.observe(owner)
            return {"items": [self.public(account)], "enabled": True}

    async def start(self, owner, session, kind):
        self.require(owner)
        async with self.locks[owner.key]:
            self.observe(owner)
            attempt = self.store.begin(
                owner, session, self.native.engines.runtime_key(owner), kind
            )
            try:
                if kind == "existing":
                    snapshot = self.native.read(owner)
                    if snapshot is None:
                        raise HubError(
                            "platform_auth_required",
                            "当前独立 Hot 没有 QQ 登录，请扫码登录",
                            409,
                        )
                    attempt.update(
                        status="confirmed",
                        uin=snapshot.uin,
                        fingerprint=snapshot.fingerprint,
                    )
                else:
                    data = await self.native.start(owner)
                    if not isinstance(data, dict) or not re.fullmatch(
                        r"[A-Za-z0-9_-]{1,256}", data.get("qrcode_id", "")
                    ):
                        raise HubError(
                            "upstream_contract", "Hot 登录会话结构不匹配", 502
                        )
                    image = base64.b64decode(data.get("qr_base64", ""), validate=True)
                    if not 24 <= len(image) <= 128 * 1024 or not image.startswith(
                        b"\x89PNG\r\n\x1a\n"
                    ):
                        raise HubError(
                            "upstream_contract", "Hot 未返回受支持的 PNG 二维码", 502
                        )
                    attempt.update(
                        status="waiting",
                        native_id=data["qrcode_id"],
                        image=base64.b64encode(image).decode(),
                    )
            except (HubError, ValueError, TypeError, binascii.Error):
                # A lost response may leave Hot's QR listener alive. This grant stays revoked.
                attempt["status"] = "error"
                self.store.save_attempt(owner, session, attempt)
                account = self.store.get(owner)
                self.store.replace(
                    owner,
                    account,
                    {**account, "attempt_id": None, "attempt_expires": 0},
                )
                raise HubError(
                    "login_unavailable",
                    "无法确认扫码结果，请稍后重新开始；不会自动关联账号",
                    503,
                ) from None
            self.store.save_attempt(owner, session, attempt)
            return self.public_attempt(attempt)

    @staticmethod
    def public_attempt(attempt):
        return {
            "id": attempt["id"],
            "status": attempt["status"],
            "uin": attempt.get("uin"),
            "expires_at": attempt["expires"],
            "binding_generation": attempt["generation"],
            "qr_path": f"/api/accounts/qq/login/{attempt['id']}/qr"
            if attempt.get("image")
            else None,
        }

    async def poll(self, owner, session, attempt_id):
        self.require(owner)
        async with self.locks[owner.key]:
            attempt, _ = self.store.current_attempt(owner, session, attempt_id)
            if attempt["status"] in {"waiting", "scanned"}:
                result = await self.native.poll(owner, attempt["native_id"])
                if not isinstance(result, dict) or result.get("status") not in {
                    "waiting",
                    "scanned",
                    "confirmed",
                    "expired",
                    "canceled",
                    "error",
                }:
                    raise HubError("upstream_contract", "Hot 登录状态无法确认", 502)
                attempt["status"] = result["status"]
                if result["status"] == "confirmed":
                    values = result.get("credentials") or {}
                    snapshot = self.native.read(owner)
                    if (
                        snapshot is None
                        or not isinstance(values, dict)
                        or snapshot.uin != values.get("uin")
                        or snapshot.credential()["musickey"] != values.get("authst")
                    ):
                        attempt["status"] = "error"
                    else:
                        attempt.update(
                            uin=snapshot.uin, fingerprint=snapshot.fingerprint
                        )
                self.store.save_attempt(owner, session, attempt)
            return self.public_attempt(attempt)

    async def image(self, owner, session, attempt_id):
        self.require(owner)
        async with self.locks[owner.key]:
            attempt, _ = self.store.current_attempt(owner, session, attempt_id)
            if not attempt.get("image") or attempt["status"] not in {
                "waiting",
                "scanned",
            }:
                raise HubError("not_found", "二维码已不可用", 404)
            return base64.b64decode(attempt["image"])

    async def bind(self, owner, session, attempt_id):
        self.require(owner)
        # Only login mutations serialize. Platform reads release the lock during network I/O,
        # so unlink invalidates in-flight replies immediately.
        async with self.locks[owner.key]:
            attempt, account = self.store.current_attempt(owner, session, attempt_id)
            if attempt["status"] == "bound" and account["state"] == "bound":
                observed, _ = self.observe(owner)
                if observed["state"] == "bound":
                    return self.public(observed)
            if attempt["status"] != "confirmed":
                raise HubError("conflict", "扫码尚未确认，不能关联账号", 409)
            snapshot = self.native.read(owner)
            if snapshot is None or snapshot.fingerprint != attempt.get("fingerprint"):
                raise HubError("conflict", "Hot 登录已变化，请重新核对账号", 409)
        # The read-only SDK verifies credentials, without refreshing or persisting them.
        await self.protocol.read(snapshot, "verify")
        async with self.locks[owner.key]:
            attempt, current = self.store.current_attempt(owner, session, attempt_id)
            latest = self.native.read(owner)
            if (
                current != account
                or latest is None
                or latest.fingerprint != snapshot.fingerprint
            ):
                raise HubError("conflict", "验证期间账号已变化，请重新核对", 409)
            bound = self.store.replace(
                owner,
                account,
                {
                    **account,
                    "state": "bound",
                    "account_ref": uuid4().hex,
                    "uin": snapshot.uin,
                    "credential_revision": 1,
                    "fingerprint": snapshot.fingerprint,
                    "attempt_expires": 0,
                },
            )
            attempt["status"] = "bound"
            attempt.pop("image", None)
            attempt.pop("native_id", None)
            self.store.save_attempt(owner, session, attempt)
            return self.public(bound)

    async def unlink(self, owner, generation):
        self.require(owner)
        async with self.locks[owner.key]:
            old = self.store.get(owner)
            if old["binding_generation"] != generation:
                raise HubError("conflict", "账号代次已变化，请刷新后操作", 409)
            result = self.store.replace(
                owner,
                old,
                {
                    **old,
                    "state": "unbound",
                    "binding_generation": generation + 1,
                    "credential_revision": 0,
                    "account_ref": None,
                    "uin": None,
                    "fingerprint": None,
                    "attempt_id": None,
                    "attempt_expires": 0,
                },
            )
            with self.store.store.db() as db:
                db.execute("DELETE FROM account_attempts WHERE owner=?", (owner.key,))
            # Do not call native logout: a still-running QR callback could recreate credentials.
            # Revocation is in this facade, not inferred from native-file emptiness.
            return self.public(result)

    async def snapshot(self, owner):
        self.require(owner)
        async with self.locks[owner.key]:
            account, snapshot = self.observe(owner)
            if account["state"] != "bound" or snapshot is None:
                raise HubError(
                    "platform_auth_required",
                    "请先关联本人 QQ 账号；不会回退公共推荐",
                    409,
                )
            return self.public(account), snapshot

    async def validate(self, owner, grant, snapshot):
        async with self.locks[owner.key]:
            current, latest = self.observe(owner)
            if (
                self.public(current) != grant
                or latest is None
                or latest.fingerprint != snapshot.fingerprint
            ):
                raise HubError(
                    "binding_changed", "请求期间账号或凭据已变化，请重新加载", 409
                )

    async def expired(self, owner, grant, snapshot):
        async with self.locks[owner.key]:
            current, latest = self.observe(owner)
            if (
                self.public(current) == grant
                and latest
                and latest.fingerprint == snapshot.fingerprint
            ):
                self.store.replace(owner, current, {**current, "state": "expired"})
