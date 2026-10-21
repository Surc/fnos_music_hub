"""Private per-user Hot runtime boundary. Actual scheduling remains in Hot."""

import os
from pathlib import Path

import httpx

from hub.domain import digest
from hub.errors import HubError


class HotEngines:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def config(self, owner):
        if (
            owner.instance_id != self.settings.instance_id
            or owner.user_guid not in self.settings.users
        ):
            raise HubError("unsupported", "管理员尚未为此用户配置独立下载引擎", 409)
        return self.settings.users[owner.user_guid]

    def runtime_key(self, owner):
        cfg = self.config(owner)
        return digest(
            {
                "instance": owner.instance_id,
                "user": owner.user_guid,
                "url": cfg.engine_url,
                "root": str(cfg.download_root),
            }
        )

    async def call(self, owner, method, path, body=None):
        cfg = self.config(owner)
        token = os.environ.get(cfg.engine_token_env, "")
        if len(token) < 16:
            raise HubError("engine_unconfigured", "独立引擎访问令牌尚未配置", 503)
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=20, trust_env=False
            ) as client:
                response = await client.request(
                    method,
                    cfg.engine_url + path,
                    headers={"Authorization": "Bearer " + token},
                    json=body,
                )
            if response.status_code == 429:
                raise HubError("rate_limited", "下载引擎暂时限制请求", 429)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            # A POST timeout may have happened after Hot persisted the task.
            raise HubError(
                "engine_unavailable", "下载引擎未返回可确认的结果", 503
            ) from None

    async def check_target(self, owner):
        snapshot = await self.call(owner, "GET", "/api/settings")
        settings = snapshot.get("settings") if isinstance(snapshot, dict) else None
        if not isinstance(settings, dict):
            raise HubError("upstream_contract", "引擎设置结构不匹配", 502)
        configured = settings.get("downloadDir")
        if (
            not isinstance(configured, str)
            or Path(configured).resolve() != self.config(owner).download_root
        ):
            raise HubError("target_mismatch", "引擎下载目录与授权目录不一致", 409)
        # This iteration implements exact-quality requests, not hidden downgrade policies.
        if settings.get("autoDowngrade", True) is not False:
            raise HubError(
                "quality_policy", "请先在独立 Hot 引擎中关闭自动音质降级", 409
            )

    async def tasks(self, owner):
        result = await self.call(owner, "GET", "/api/tasks")
        if not isinstance(result, list) or any(
            not isinstance(t, dict) or not isinstance(t.get("id"), str) for t in result
        ):
            raise HubError("upstream_contract", "引擎任务结构不匹配", 502)
        return result
