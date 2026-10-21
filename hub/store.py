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
            if version not in (0, 1):
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
              PRAGMA user_version=1;
            """)
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
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
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

    def logout(self, sid):
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (self.session_hash(sid),))

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
        assert table in {"manifests", "tasks", "assets"}
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
            rows = db.execute("SELECT payload FROM tasks ORDER BY rowid").fetchall()
        return [
            t
            for row in rows
            if (t := json.loads(row[0]))["status"] not in {"completed", "failed"}
        ]

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
