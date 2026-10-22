"""Read immutable snapshots from the dedicated Hot store. Never write/refresh it."""

import json
import os
import stat
from dataclasses import dataclass, field

from hub.domain import digest
from hub.errors import HubError
from hub.paths import engine_directory


@dataclass(frozen=True, repr=False)
class CredentialSnapshot:
    uin: str
    values: tuple = field(repr=False)
    source_digest: str = field(default="", repr=False)

    @property
    def fingerprint(self):
        return self.source_digest or digest(dict(self.values))

    def credential(self):
        # Caller receives a fresh value. Neither SDK nor browser can mutate this snapshot.
        return dict(self.values)


class HotQqCredentials:
    def __init__(self, settings, engines):
        self.settings, self.engines = settings, engines

    def read(self, owner):
        self.engines.config(owner)
        parent = engine_directory(self.settings, owner.user_guid)
        try:
            # Reject symlinked components, permissive stores, special files and oversized input.
            directory = os.open(
                self.settings.data_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                for part in (None, "engines", parent.name):
                    if part is not None:
                        child = os.open(
                            part,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory,
                        )
                        os.close(directory)
                        directory = child
                    info = os.fstat(directory)
                    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                        raise OSError("unsafe credential directory")
                fd = os.open(
                    "qq-credentials.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
                )
            finally:
                os.close(directory)
            with os.fdopen(fd, "rb") as file:
                info = os.fstat(file.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077
                    or info.st_size > 65536
                ):
                    raise OSError("unsafe credential file")
                data = file.read(65537)
            if len(data) > 65536:
                raise ValueError("oversized credential file")
            raw = json.loads(data)
            if not isinstance(raw, dict):
                raise ValueError("invalid credential store")
            uin, authst = raw.get("loginUin", ""), raw.get("authst", "")
            if not uin and not authst:
                return None
            if (
                not isinstance(uin, str)
                or not uin.isascii()
                or not uin.isdecimal()
                or not 0 < int(uin) < 2**64
                or not isinstance(authst, str)
                or not 1 <= len(authst) <= 8192
            ):
                raise ValueError("invalid login identity")
            source = raw.get("loginResponseData") or {}
            if not isinstance(source, dict):
                raise ValueError("invalid login response")
            values = {"musicid": int(uin), "str_musicid": uin, "musickey": authst}
            # Read-only catalog gets no refresh/access tokens: only Hot owns them.
            for original, target in (
                ("loginType", "login_type"),
                ("encryptUin", "encrypt_uin"),
            ):
                if original in source:
                    value = source[original]
                    if original == "loginType" and type(value) is not int:
                        raise ValueError("invalid login type")
                    if original == "encryptUin" and not isinstance(value, str):
                        raise ValueError("invalid encrypted identity")
                    values[target] = value
            source_digest = digest(
                {
                    key: raw.get(key)
                    for key in (
                        "loginUin",
                        "authst",
                        "refreshToken",
                        "refreshKey",
                        "accessToken",
                        "openid",
                        "loginResponseData",
                    )
                }
            )
            return CredentialSnapshot(uin, tuple(sorted(values.items())), source_digest)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, OverflowError):
            raise HubError(
                "credential_store_unavailable", "独立 Hot 账号存储不可安全读取", 503
            ) from None

    async def start(self, owner):
        return await self.engines.call(owner, "POST", "/api/login/qr", {})

    async def poll(self, owner, native_id):
        return await self.engines.call(owner, "GET", "/api/login/qr/" + native_id)
