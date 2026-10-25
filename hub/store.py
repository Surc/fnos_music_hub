"""SQLite owns authorization projections and a durable dispatch outbox, not Hot's queue."""

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from .domain import canonical, digest, now
from .errors import HubError

DATABASE_SCHEMA = 3


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        keyfile = directory / "vault.key"
        try:
            fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
        os.chmod(keyfile, 0o600)
        self.vault = Fernet(keyfile.read_bytes())
        self.path = directory / "hub.sqlite3"
        with self.db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, DATABASE_SCHEMA):
                raise RuntimeError(
                    "unsupported database schema; restore a compatible backup"
                )
            db.executescript("""
              CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, token BLOB NOT NULL,
                csrf TEXT NOT NULL, expires REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS songs (
                owner TEXT NOT NULL, track_key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(owner, track_key));
              CREATE TABLE IF NOT EXISTS manifests (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, idem TEXT NOT NULL,
                request_hash TEXT NOT NULL, payload TEXT NOT NULL,
                UNIQUE(owner, idem));
              CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS favorites (
                owner TEXT NOT NULL, track_key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(owner, track_key));
              CREATE TABLE IF NOT EXISTS accounts (
                owner TEXT NOT NULL, provider TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(owner, provider));
              CREATE TABLE IF NOT EXISTS account_attempts (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, session TEXT NOT NULL,
                payload BLOB NOT NULL);
              CREATE TABLE IF NOT EXISTS playlist_captures (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, idem TEXT NOT NULL,
                payload TEXT NOT NULL, UNIQUE(owner, idem));
              CREATE INDEX IF NOT EXISTS captures_owner ON playlist_captures(owner);
              CREATE INDEX IF NOT EXISTS captures_source ON playlist_captures(
                owner, json_extract(payload, '$.source.id'),
                json_extract(payload, '$.source.dirid'));
              CREATE INDEX IF NOT EXISTS tasks_active ON tasks(id)
                WHERE json_extract(payload, '$.status') NOT IN ('completed','failed');
            """)
            db.execute(f"PRAGMA user_version={DATABASE_SCHEMA}")
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def session_hash(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def new_session(self, principal, token, lifetime):
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute(
                "SELECT id FROM sessions WHERE expires <= ?", (time.time(),)
            ).fetchall()
            for row in expired:
                self._revoke_session(db, row[0])
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?)",
                (
                    self.session_hash(sid),
                    principal.key,
                    self.vault.encrypt(token.encode()),
                    csrf,
                    time.time() + lifetime,
                ),
            )
        return sid, csrf

    def session(self, sid):
        if not sid or len(sid) > 256:
            raise HubError("auth_required", "请登录飞牛音乐账号", 401)
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE id=? AND expires>?",
                (self.session_hash(sid), time.time()),
            ).fetchone()
        if row is None:
            raise HubError("auth_required", "会话已失效，请重新登录", 401)
        result = dict(row)
        try:
            result["token"] = self.vault.decrypt(result["token"]).decode()
        except InvalidToken:
            raise HubError("auth_required", "会话无法解密，请重新登录", 401) from None
        return result

    def check_session(self, session, db=None):
        """Recheck the original local grant after awaited work, before publication."""
        if db is None:
            with self.db() as connection:
                return self.check_session(session, connection)
        valid = db.execute(
            "SELECT 1 FROM sessions WHERE id=? AND owner=? AND csrf=? AND expires>?",
            (session["id"], session["owner"], session["csrf"], time.time()),
        ).fetchone()
        if valid is None:
            raise HubError("auth_required", "会话已失效，请重新登录", 401)

    @staticmethod
    def _revoke_session(db, session_id):
        # Revoke only the still-current candidate owned by this session. An old
        # session must not erase another session's new candidate or a bound account.
        rows = db.execute(
            "SELECT id,owner FROM account_attempts WHERE session=?", (session_id,)
        ).fetchall()
        for attempt in rows:
            row = db.execute(
                "SELECT payload FROM accounts WHERE owner=? AND json_extract(payload, '$.attempt_id')=?",
                (attempt["owner"], attempt["id"]),
            ).fetchone()
            if row:
                account = json.loads(row[0])
                if (
                    account.get("attempt_id") == attempt["id"]
                    and account["state"] != "bound"
                ):
                    account.update(
                        attempt_id=None,
                        attempt_expires=0,
                        binding_generation=account["binding_generation"] + 1,
                    )
                    db.execute(
                        "UPDATE accounts SET payload=? WHERE owner=? AND provider=?",
                        (canonical(account), attempt["owner"], account["provider"]),
                    )
        db.execute("DELETE FROM account_attempts WHERE session=?", (session_id,))
        db.execute("DELETE FROM sessions WHERE id=?", (session_id,))

    def logout(self, sid):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._revoke_session(db, self.session_hash(sid))

    def cache_song(self, owner, song):
        from .domain import TrackRef

        key = TrackRef.model_validate(song["track"]).key
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO songs VALUES(?,?,?)",
                (owner.key, key, canonical(song)),
            )

    def song(self, owner, track):
        with self.db() as db:
            row = db.execute(
                "SELECT payload FROM songs WHERE owner=? AND track_key=?",
                (owner.key, track.key),
            ).fetchone()
        if row is None:
            raise HubError("not_found", "请先搜索并选择该曲目", 404)
        return json.loads(row[0])

    def save_manifest(self, owner, manifest):
        with self.db() as db:
            db.execute(
                "INSERT INTO manifests VALUES(?,?,?)",
                (manifest["snapshot_id"], owner.key, canonical(manifest)),
            )

    def manifest(self, owner, id):
        return self._owned("manifests", owner.key, id)

    def _owned(self, table, owner_key, id):
        assert table in {"manifests", "tasks", "assets", "playlist_captures"}
        with self.db() as db:
            row = db.execute(
                f"SELECT payload FROM {table} WHERE id=? AND owner=?", (id, owner_key)
            ).fetchone()
        if row is None:
            raise HubError("not_found", "记录不存在或不属于当前用户", 404)
        return json.loads(row[0])

    def owned_list(self, table, owner):
        assert table in {"tasks", "assets", "favorites"}
        with self.db() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    f"SELECT payload FROM {table} WHERE owner=? ORDER BY rowid DESC LIMIT 500",
                    (owner.key,),
                )
            ]

    def submit(self, owner, request, manifest, idem, runtime_key):
        if not idem or len(idem) > 128:
            raise HubError("invalid_request", "需要长度不超过 128 的 Idempotency-Key")
        request_hash = digest(
            {"request": request.model_dump(), "manifest": manifest["content_hash"]}
        )
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT request_hash,payload FROM tasks WHERE owner=? AND idem=?",
                (owner.key, idem),
            ).fetchone()
            if row:
                if row[0] != request_hash:
                    raise HubError("conflict", "同一幂等键对应了不同下载内容", 409)
                return json.loads(row[1]), False
            task = {
                "id": uuid4().hex,
                "owner": owner.model_dump(),
                "created_at": now(),
                "quality": request.quality,
                "target_ref": request.target_ref,
                "runtime_key": runtime_key,
                "manifest": manifest,
                "status": "queued",
                "entries": [
                    {
                        "occurrence_id": e["occurrence_id"],
                        "status": "queued",
                        "engine_id": None,
                        "song": e["song"],
                        "asset_id": None,
                        "error": None,
                    }
                    for e in manifest["ordered_entries"]
                ],
            }
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?)",
                (task["id"], owner.key, idem, request_hash, canonical(task)),
            )
        return task, True

    def replay(self, owner, request, manifest, idem):
        """Return an already accepted intent even while its engine is offline."""
        with self.db() as db:
            row = db.execute(
                "SELECT request_hash,payload FROM tasks WHERE owner=? AND idem=?",
                (owner.key, idem),
            ).fetchone()
        if row is None:
            return None
        expected = digest(
            {"request": request.model_dump(), "manifest": manifest["content_hash"]}
        )
        if row[0] != expected:
            raise HubError("conflict", "同一幂等键对应了不同下载内容", 409)
        return json.loads(row[1])

    def pending(self):
        with self.db() as db:
            rows = db.execute(
                "SELECT payload FROM tasks INDEXED BY tasks_active WHERE json_extract(payload, '$.status') "
                "NOT IN ('completed','failed') ORDER BY rowid"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_task(self, task):
        with self.db() as db:
            db.execute(
                "UPDATE tasks SET payload=? WHERE id=?", (canonical(task), task["id"])
            )

    def save_asset(self, owner_key, asset):
        with self.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO assets VALUES(?,?,?)",
                (asset["id"], owner_key, canonical(asset)),
            )

    def favorite(self, owner, track, enabled):
        song = self.song(owner, track) if enabled else None
        with self.db() as db:
            if enabled:
                db.execute(
                    "INSERT OR REPLACE INTO favorites VALUES(?,?,?)",
                    (owner.key, track.key, canonical(song)),
                )
            else:
                db.execute(
                    "DELETE FROM favorites WHERE owner=? AND track_key=?",
                    (owner.key, track.key),
                )

    def begin_capture(self, owner, source, grant, idem):
        if not idem or len(idem) > 128:
            raise HubError("invalid_request", "需要长度不超过 128 的 Idempotency-Key")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM playlist_captures WHERE owner=? AND idem=?",
                (owner.key, idem),
            ).fetchone()
            if row:
                capture = json.loads(row[0])
                if capture["source"] != source or any(
                    capture["account"][key] != grant[key]
                    for key in ("account_ref", "binding_generation", "uin")
                ):
                    raise HubError("conflict", "此快照请求对应不同歌单或账号关联", 409)
                return capture
            capture = {
                "id": uuid4().hex,
                "source": source,
                "account": grant,
                "created_at": now(),
                "status": "pending",
                "complete": False,
                "attempt": 0,
                "pass": 0,
                "fetched_count": 0,
                "manifest_id": None,
                "error": None,
                "retry_at": 0,
            }
            db.execute(
                "INSERT INTO playlist_captures VALUES(?,?,?,?)",
                (capture["id"], owner.key, idem, canonical(capture)),
            )
            return capture

    def capture(self, owner, capture_id):
        return self._owned("playlist_captures", owner.key, capture_id)

    def captures(self, owner, source=None, before=None, limit=20):
        if not 1 <= limit <= 50:
            raise HubError("invalid_request", "历史每页需要 1 至 50 条")
        where, args = ["owner=?"], [owner.key]
        if source is not None:
            where.extend(
                [
                    "json_extract(payload, '$.source.id')=?",
                    "json_extract(payload, '$.source.dirid')=?",
                ]
            )
            args.extend([source["id"], source["dirid"]])
        with self.db() as db:
            if before:
                cursor = db.execute(
                    "SELECT rowid, payload FROM playlist_captures WHERE id=? AND owner=?",
                    (before, owner.key),
                ).fetchone()
                if cursor is None or (
                    source is not None and json.loads(cursor[1])["source"] != source
                ):
                    raise HubError("not_found", "历史游标不存在或不属于此列表", 404)
                where.append("rowid<?")
                args.append(cursor[0])
            where.append("json_extract(payload, '$.status')!='deleted'")
            rows = db.execute(
                "SELECT payload FROM playlist_captures WHERE "
                + " AND ".join(where)
                + " ORDER BY rowid DESC LIMIT ?",
                (*args, limit + 1),
            ).fetchall()
        result = [json.loads(row[0]) for row in rows[:limit]]
        return {
            "items": result,
            "next_cursor": result[-1]["id"] if len(rows) > limit else None,
        }

    def remove_capture(self, owner, capture_id):
        # Keep a small tombstone: a lost DELETE reply/reused creation key cannot
        # repeat platform reads, and deleting a limited attempt cannot erase cooldown.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM playlist_captures WHERE id=? AND owner=?",
                (capture_id, owner.key),
            ).fetchone()
            if row is None:
                raise HubError("not_found", "记录不存在或不属于当前用户", 404)
            capture = json.loads(row[0])
            if capture["manifest_id"]:
                db.execute(
                    "DELETE FROM manifests WHERE id=? AND owner=?",
                    (capture["manifest_id"], owner.key),
                )
            capture.update(
                status="deleted", complete=False, manifest_id=None, error=None
            )
            db.execute(
                "UPDATE playlist_captures SET payload=? WHERE id=? AND owner=?",
                (canonical(capture), capture_id, owner.key),
            )
            return capture

    def capture_retry_at(self, owner):
        with self.db() as db:
            row = db.execute(
                "SELECT MAX(json_extract(payload, '$.retry_at')) FROM playlist_captures WHERE owner=?",
                (owner.key,),
            ).fetchone()
        return row[0] or 0

    def save_capture(self, owner, capture, manifest=None):
        # Publish the final immutable manifest and its handle in one transaction.
        # A crash can leave a reading record, never a complete record without its manifest.
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if manifest is not None:
                db.execute(
                    "INSERT INTO manifests VALUES(?,?,?)",
                    (manifest["snapshot_id"], owner.key, canonical(manifest)),
                )
            db.execute(
                "UPDATE playlist_captures SET payload=? WHERE id=? AND owner=?",
                (canonical(capture), capture["id"], owner.key),
            )
