"""Monotonic binding generations with encrypted, session-scoped login attempts."""

import json
import time
from uuid import uuid4

from cryptography.fernet import InvalidToken

from .domain import canonical
from .errors import HubError


class AccountStore:
    def __init__(self, store):
        self.store = store

    def get(self, owner):
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM accounts WHERE owner=? AND provider='qq'",
                (owner.key,),
            ).fetchone()
        return (
            json.loads(row[0])
            if row
            else {
                "provider": "qq",
                "state": "unbound",
                "binding_generation": 0,
                "credential_revision": 0,
                "account_ref": None,
                "uin": None,
            }
        )

    def replace(self, owner, expected, value):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM accounts WHERE owner=? AND provider='qq'",
                (owner.key,),
            ).fetchone()
            current = json.loads(row[0]) if row else self.get(owner)
            if current != expected:
                raise HubError("conflict", "账号状态已变化，请刷新后核对", 409)
            db.execute(
                "INSERT OR REPLACE INTO accounts VALUES(?,'qq',?)",
                (owner.key, canonical(value)),
            )
        return value

    def attempt(self, owner, session, attempt_id):
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM account_attempts WHERE id=? AND owner=? AND session=?",
                (attempt_id, owner.key, session["id"]),
            ).fetchone()
        if row is None:
            raise HubError("not_found", "登录尝试不存在或不属于当前会话", 404)
        try:
            return json.loads(self.store.vault.decrypt(row[0]))
        except (InvalidToken, ValueError, TypeError):
            raise HubError(
                "auth_required", "登录尝试无法读取，请重新开始", 409
            ) from None

    def save_attempt(self, owner, session, attempt):
        with self.store.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO account_attempts VALUES(?,?,?,?)",
                (
                    attempt["id"],
                    owner.key,
                    session["id"],
                    self.store.vault.encrypt(canonical(attempt).encode()),
                ),
            )

    def begin(self, owner, session, runtime_key, kind):
        old = self.get(owner)
        if old["state"] == "bound":
            raise HubError("conflict", "请先解除当前 QQ 关联，再登录或换号", 409)
        if old.get("attempt_expires", 0) > time.time():
            raise HubError("conflict", "已有登录尝试，请先继续或取消", 409)
        attempt = {
            "id": uuid4().hex,
            "generation": old["binding_generation"] + 1,
            "expires": time.time() + 180,
            "status": "starting",
            "kind": kind,
        }
        self.replace(
            owner,
            old,
            {
                **old,
                "state": "unbound",
                "account_ref": None,
                "uin": None,
                "binding_generation": attempt["generation"],
                "credential_revision": 0,
                "runtime_key": runtime_key,
                "attempt_id": attempt["id"],
                "attempt_expires": attempt["expires"],
            },
        )
        self.save_attempt(owner, session, attempt)
        return attempt

    def current_attempt(self, owner, session, attempt_id):
        attempt, account = self.attempt(owner, session, attempt_id), self.get(owner)
        if (
            account["binding_generation"] != attempt["generation"]
            or account.get("attempt_id") != attempt_id
        ):
            raise HubError("conflict", "此登录尝试已撤销，不能绑定账号", 409)
        if attempt["expires"] <= time.time() and attempt["status"] != "bound":
            raise HubError("login_expired", "登录尝试已过期，请重新开始", 409)
        return attempt, account
