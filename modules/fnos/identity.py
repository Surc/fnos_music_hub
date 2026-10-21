"""Client for the pinned Yinqiao API, without copying its signer or auth implementation."""

import hashlib
import os
import re

import httpx

from hub.domain import Principal
from hub.errors import HubError


class BridgeIdentity:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def call(self, method, path, token=None, body=None):
        headers = {"Accept": "application/json"}
        key = os.environ.get(self.settings.bridge_key_env)
        if key:
            headers["X-Yinqiao-Key"] = key
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            # No shared cookie jar: one fnOS user's upstream cookies cannot reach another.
            async with httpx.AsyncClient(
                transport=self.transport, timeout=15, trust_env=False
            ) as client:
                result = await client.request(
                    method, self.settings.bridge_url + path, headers=headers, json=body
                )
            if result.status_code in (401, 403):
                raise HubError("auth_required", "飞牛身份验证未通过，请重新登录", 401)
            result.raise_for_status()
            envelope = result.json()
            if not isinstance(envelope, dict) or envelope.get("ok") is not True:
                raise ValueError("invalid envelope")
            return envelope["data"]
        except (httpx.HTTPError, ValueError, KeyError):
            raise HubError(
                "identity_unavailable", "无法验证飞牛身份，操作已暂停", 503
            ) from None

    async def current(self, token):
        user = await self.call("GET", "/auth/me", token)
        guid = user.get("guid") if isinstance(user, dict) else None
        if (
            not isinstance(guid, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", guid)
            or guid.lower() in {"shared", "admin", "unknown", "anonymous"}
        ):
            raise HubError(
                "auth_required", "飞牛未返回可信用户 GUID，拒绝建立用户归属", 401
            )
        return Principal(instance_id=self.settings.instance_id, user_guid=guid)

    async def login(self, username, password, device_id):
        # Yinqiao expects the official SHA-256 representation; never persist the password.
        data = await self.call(
            "POST",
            "/auth/login/password",
            body={
                "username": username,
                "password": hashlib.sha256(password.encode()).hexdigest(),
                "deviceId": device_id,
            },
        )
        token = data.get("userToken") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token.strip() or len(token) > 8192:
            raise HubError("auth_required", "飞牛未返回有效会话", 401)
        return await self.current(token), token
