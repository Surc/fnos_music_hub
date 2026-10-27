#!/usr/bin/env python3
"""fnOS-only lifecycle supervisor. No platform login, migration or Socket ownership."""

import argparse
import contextlib
import fcntl
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

PROGRAM = Path(__file__).resolve().parents[1]
PORT = 8790


class NeteaseDependenciesMissing(RuntimeError):
    """Safe startup classification; never expose SDK errors or credentials."""


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".new-" + secrets.token_hex(4))
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, sort_keys=True, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path):
    return json.loads(path.read_text())


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise RuntimeError("external_symlink")
            result[rel] = {"link": os.readlink(path)}
        elif path.is_file():
            with path.open("rb") as file:
                sha = hashlib.file_digest(file, "sha256").hexdigest()
            result[rel] = {"sha256": sha, "mode": path.stat().st_mode & 0o777}
        elif not path.is_dir():
            raise RuntimeError("non_regular_file")
    return result


def identity(pid):
    """A PID alone is never authority to send a signal."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat.rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return {
            "pid": pid,
            "start": fields[19],
            "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "uid": Path(f"/proc/{pid}").stat().st_uid,
        }
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def alive(record):
    return bool(record and identity(record["pid"]) == record)


def send_signal(record, sig):
    if not record:
        return
    # Pin the kernel process before checking its start time; no PID-reuse gap.
    try:
        fd = os.pidfd_open(record["pid"])
    except ProcessLookupError:
        return
    try:
        if alive(record) and record["uid"] == os.getuid():
            signal.pidfd_send_signal(fd, sig)
    finally:
        os.close(fd)


def get_json(url, *, host=None, token=None):
    headers = {}
    if host:
        headers["Host"] = host
    if token:
        headers["Authorization"] = "Bearer " + token
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # Only validated, fixed loopback addresses are passed here.
    with opener.open(urllib.request.Request(url, headers=headers), timeout=1) as res:
        return json.loads(res.read(65536))


class Lifecycle:
    def __init__(self, program=PROGRAM):
        self.program = program.resolve()
        self.target = Path(os.environ["TRIM_APPDEST"]).resolve(strict=True)
        self.var = Path(os.environ["TRIM_PKGVAR"]).resolve()
        if self.var == Path("/") or self.var.is_relative_to(self.target):
            raise RuntimeError("invalid_data_directory")
        self.config = self.var / "config"
        self.state = self.var / "state"
        self.run = self.var / "run"
        self.registry = self.run / "processes.json"
        self.active = self.var / "active-program"
        self.rollback_point = self.var / "rollback"

    def guard(self):
        if os.getuid() == 0:
            raise RuntimeError("package_user_required")
        if int(Path("/proc/self/stat").read_text().split()[0]) != os.getpid():
            raise RuntimeError("matching_proc_pid_namespace_required")
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise RuntimeError("linux_pidfd_required")
        for path in (self.var, self.config, self.state, self.run):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.is_symlink() or path.stat().st_uid != os.getuid():
                raise RuntimeError("private_directory_required")
            os.chmod(path, 0o700)

    @contextlib.contextmanager
    def lock(self, name="action.lock"):
        with (self.run / name).open("a") as file:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def activate(self, program):
        resolved = program.resolve(strict=True)
        if resolved != self.target and not resolved.is_relative_to(
            self.var / "backups"
        ):
            raise RuntimeError("invalid_program_slot")
        temp = self.var / (".active-" + secrets.token_hex(4))
        temp.symlink_to(resolved, target_is_directory=True)
        os.replace(temp, self.active)

    def settings(self):
        sys.path[:0] = [
            str(self.program / "server"),
            str(self.program / "runtime/site-packages"),
        ]
        from hub.config import Settings

        file = self.config / "hub.json"
        cfg = Settings.load(str(file))
        if cfg.data_dir != self.state or not cfg.secure_cookie:
            raise RuntimeError("native_private_state_and_https_required")
        for user in cfg.users.values():
            port = urlsplit(user.engine_url).port
            if not port or not 1024 <= port <= 65535 or port == PORT:
                raise RuntimeError("invalid_hot_port")
            if not user.download_root.is_relative_to(self.var / "downloads"):
                raise RuntimeError("native_private_download_directory_required")
            if not re.fullmatch(r"HUB_HOT_[A-Z0-9_]+", user.engine_token_env):
                raise RuntimeError("invalid_token_variable")
        if len({x.engine_token_env for x in cfg.users.values()}) != len(cfg.users):
            raise RuntimeError("distinct_hot_tokens_required")
        if not re.fullmatch(r"HUB_BRIDGE_[A-Z0-9_]+", cfg.bridge_key_env):
            raise RuntimeError("invalid_bridge_key_variable")
        return cfg

    def secrets(self, cfg):
        file = self.config / "secrets.json"
        values = read_json(file) if file.exists() else {}
        for user in cfg.users.values():
            key = user.engine_token_env
            if key not in values:
                values[key] = secrets.token_urlsafe(32)
            if not isinstance(values[key], str) or len(values[key]) < 16:
                raise RuntimeError("invalid_hot_token")
        if not all(
            isinstance(k, str) and isinstance(v, str) for k, v in values.items()
        ):
            raise RuntimeError("invalid_secrets")
        atomic_json(file, values)
        return values

    def base_env(self):
        return {
            "PATH": f"{self.program}/bin:{self.program}/runtime/python/bin:/usr/bin:/bin",
            "HOME": str(self.var / "home"),
            "LANG": "C.UTF-8",
            "PYTHONPATH": f"{self.program}/server:{self.program}/runtime/site-packages",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "SSL_CERT_FILE": str(
                self.program / "runtime/site-packages/certifi/cacert.pem"
            ),
            "TRIM_APPDEST": str(self.target),
            "TRIM_PKGVAR": str(self.var),
        }

    def install(self):
        file = self.config / "hub.json"
        if not file.exists():
            if (self.state / "hub.sqlite3").exists():
                raise RuntimeError("restore_matching_config_before_reinstall")
            atomic_json(
                file,
                {
                    "instance_id": secrets.token_hex(16),
                    "data_dir": str(self.state),
                    "bridge_url": os.environ.get("wizard_bridge_url", ""),
                    "bridge_key_env": "HUB_BRIDGE_KEY",
                    "public_origin": os.environ.get("wizard_public_origin", ""),
                    "secure_cookie": True,
                    "admin_guids": [],
                    "users": {},
                    "qq_accounts_enabled": False,
                    "netease_enabled": False,
                },
            )
            try:
                self.settings()
            except Exception:
                file.unlink()
                raise
        cfg = self.settings()
        self.secrets(cfg)
        self.launch_page(cfg)
        self.activate(self.program)

    def launch_page(self, cfg):
        origin = html.escape(cfg.public_origin, quote=True)
        (self.target / "ui/launch.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>音乐 Hub PREVIEW</title>'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<h1>音乐 Hub PREVIEW</h1><p>从独立 HTTPS 入口打开并登录：</p>"
            f'<p><a rel="noopener noreferrer" href="{origin}/">打开音乐 Hub</a></p>'
            "<p>若无法访问，请检查反向代理是否转发到 127.0.0.1:8790。</p>"
            "<p>本预览版的 J4125 实机验收尚未完成。</p>",
            encoding="utf-8",
        )
        os.chmod(self.target / "ui/launch.html", 0o644)

    def preflight(self):
        if os.uname().machine != "x86_64":
            raise RuntimeError("linux_amd64_required")
        cfg = self.settings()
        env = self.base_env()
        # Load real native extensions and run the packaged media tools, offline.
        subprocess.run(
            [
                str(self.program / "runtime/python/bin/python3"),
                "-sB",
                "-c",
                "import ssl, sqlite3, pydantic_core, cryptography, qqmusic_api; "
                "from cryptography.fernet import Fernet; "
                "f=Fernet(Fernet.generate_key()); assert f.decrypt(f.encrypt(b'ok'))==b'ok'",
            ],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if cfg.netease_enabled:
            try:
                subprocess.run(
                    [str(self.program / "runtime/python/bin/python3"), "-sB",
                     str(self.program / "native/dependency_probe.py"), "--netease"],
                    env=env, check=True, timeout=20,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                raise NeteaseDependenciesMissing() from None
        for tool in ("ffmpeg", "ffprobe"):
            subprocess.run(
                [str(self.program / "bin" / tool), "-version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return cfg

    def records(self):
        if not self.registry.exists():
            return {}
        return read_json(self.registry)

    def health(self, cfg, values):
        hub = get_json(
            f"http://127.0.0.1:{PORT}/healthz", host=urlsplit(cfg.public_origin).netloc
        )
        if hub.get("status") != "ok" or hub.get("version") != "0.1.0a1":
            return False
        for engine in cfg.users.values():
            if get_json(engine.engine_url + "/healthz").get("status") != "ok":
                return False
            snapshot = get_json(
                engine.engine_url + "/api/settings",
                token=values[engine.engine_token_env],
            ).get("settings", {})
            if snapshot.get("autoDowngrade") is not False:
                return False
            if Path(snapshot.get("downloadDir", "")).resolve() != engine.download_root:
                return False
        return True

    def running(self, check_health=True):
        record = self.records()
        if not record.get("ready") or not alive(record.get("supervisor")):
            return False
        if not record.get("children") or not all(alive(x) for x in record["children"]):
            return False
        if check_health:
            try:
                cfg = self.settings()
                return self.health(cfg, read_json(self.config / "secrets.json"))
            except Exception:
                return False
        return True

    def stop(self):
        record = self.records()
        entries = [record.get("supervisor"), *record.get("children", [])]
        send_signal(record.get("supervisor"), signal.SIGTERM)
        deadline = time.monotonic() + 12
        while any(alive(x) for x in entries) and time.monotonic() < deadline:
            time.sleep(0.1)
        for item in entries:
            send_signal(item, signal.SIGTERM)
        deadline = time.monotonic() + 4
        while any(alive(x) for x in entries) and time.monotonic() < deadline:
            time.sleep(0.1)
        for item in entries:
            send_signal(item, signal.SIGKILL)
        deadline = time.monotonic() + 2
        while any(alive(x) for x in entries) and time.monotonic() < deadline:
            time.sleep(0.05)
        if any(alive(x) for x in entries):
            raise RuntimeError("process_stop_failed")
        self.registry.unlink(missing_ok=True)

    @staticmethod
    def check_ports(cfg):
        ports = [PORT, *(urlsplit(e.engine_url).port for e in cfg.users.values())]
        # TIME_WAIT belongs to closed connections, not an active listening owner.
        # SO_REUSEADDR permits restart while still refusing an existing listener.
        with contextlib.ExitStack() as stack:
            for port in ports:
                sock = stack.enter_context(socket.socket())
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))

    def start(self):
        if self.running():
            return
        self.stop()  # Clean only identities recorded by this application.
        cfg = self.preflight()
        self.secrets(cfg)
        self.check_ports(cfg)
        env = self.base_env()
        process = subprocess.Popen(
            [
                str(self.program / "runtime/python/bin/python3"),
                "-sB",
                str(self.program / "native/service.py"),
                "supervise",
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.stop()
                raise RuntimeError("supervisor_start_failed")
            if self.running():
                return
            time.sleep(0.2)
        self.stop()
        raise RuntimeError("health_timeout")

    def supervise(self):
        with self.lock("supervisor.lock"):
            cfg = self.settings()
            values = self.secrets(cfg)
            env = self.base_env()
            children = []
            stop = False

            def request_stop(*_):
                nonlocal stop
                stop = True

            signal.signal(signal.SIGTERM, request_stop)
            signal.signal(signal.SIGINT, request_stop)
            record = {
                "supervisor": identity(os.getpid()),
                "children": [],
                "ready": False,
            }
            if not record["supervisor"]:
                raise RuntimeError("process_identity_unavailable")
            atomic_json(self.registry, record)

            def spawn(command, child_env):
                process = subprocess.Popen(
                    command,
                    env=child_env,
                    cwd=self.program,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                children.append(process)
                child_id = identity(process.pid)
                if child_id is None:
                    raise RuntimeError("child_identity_unavailable")
                record["children"].append(child_id)
                atomic_json(self.registry, record)

            try:
                python = str(self.program / "runtime/python/bin/python3")
                for guid, engine in cfg.users.items():
                    # Each Hot receives only its own token; never another user's secrets.
                    hot_env = {
                        **env,
                        engine.engine_token_env: values[engine.engine_token_env],
                    }
                    spawn(
                        [
                            python,
                            "-sB",
                            str(self.program / "server/scripts/run_hot_user.py"),
                            "--config",
                            str(self.config / "hub.json"),
                            "--guid",
                            guid,
                            "--binary",
                            str(self.program / "bin/hotdownloader-server"),
                        ],
                        hot_env,
                    )
                hub_env = {
                    **env,
                    **{
                        key: values[key]
                        for key in [
                            cfg.bridge_key_env,
                            *(e.engine_token_env for e in cfg.users.values()),
                        ]
                        if key in values
                    },
                }
                spawn(
                    [
                        python,
                        "-sB",
                        "-m",
                        "hub",
                        "--config",
                        str(self.config / "hub.json"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(PORT),
                    ],
                    hub_env,
                )
                deadline = time.monotonic() + 40
                while not stop and all(p.poll() is None for p in children):
                    if not record["ready"]:
                        try:
                            record["ready"] = self.health(cfg, values)
                        except Exception:
                            pass
                        if record["ready"]:
                            atomic_json(self.registry, record)
                        elif time.monotonic() > deadline:
                            raise RuntimeError("health_timeout")
                    time.sleep(0.2)
                if not stop:
                    raise RuntimeError("child_exited")
            finally:
                for process in children:
                    if process.poll() is None:
                        process.terminate()
                deadline = time.monotonic() + 8
                for process in children:
                    try:
                        process.wait(timeout=max(0.1, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                self.registry.unlink(missing_ok=True)

    def backup(self):
        self.stop()
        # Refuse a backup while a separately launched gateway holds the same state.
        with (self.state / "instance.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            parent = self.var / "backups"
            parent.mkdir(mode=0o700, exist_ok=True)
            snapshot = parent / (
                time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                + "-"
                + secrets.token_hex(4)
            )
            snapshot.mkdir(mode=0o700)
            for name, source in (
                ("program", self.program),
                ("config", self.config),
                ("state", self.state),
            ):
                inventory(source)  # Reject external links/special files before copying.
                shutil.copytree(source, snapshot / name, symlinks=True)
            atomic_json(
                snapshot / "complete.json",
                {
                    "schema": 1,
                    "content": inventory(snapshot),
                    "package_version": read_json(self.program / "bundle.json")[
                        "package_version"
                    ],
                },
            )
            temporary = self.var / (".rollback-" + secrets.token_hex(4))
            temporary.symlink_to(snapshot, target_is_directory=True)
            os.replace(temporary, self.rollback_point)
            # The old runnable program survives replacement of target by fnOS.
            self.activate(snapshot / "program")
            return snapshot

    def validated_snapshot(self):
        snapshot = self.rollback_point.resolve(strict=True)
        if not snapshot.is_relative_to((self.var / "backups").resolve()):
            raise RuntimeError("invalid_rollback_point")
        complete = read_json(snapshot / "complete.json")
        content = inventory(snapshot)
        content.pop("complete.json", None)
        if complete.get("schema") != 1 or content != complete["content"]:
            raise RuntimeError("backup_integrity_failed")
        return snapshot

    def finish_upgrade(self):
        self.validated_snapshot()
        self.launch_page(self.settings())
        self.start()
        self.activate(self.program)

    def rollback(self):
        self.stop()
        snapshot = self.validated_snapshot()
        # Immutable backup is never modified. Retry is safe after an interrupted copy/swap.
        for name in ("config", "state"):
            target = self.var / name
            restored = self.var / (".restore-" + name + "-" + secrets.token_hex(4))
            shutil.copytree(snapshot / name, restored, symlinks=True)
            if target.exists():
                failed = self.var / ("failed-" + name + "-" + secrets.token_hex(4))
                os.replace(target, failed)
            os.replace(restored, target)
        self.activate(snapshot / "program")
        # This method must run from the saved old program, via the shell fallback.
        if self.program != snapshot / "program":
            raise RuntimeError("rollback_requires_saved_program")
        self.launch_page(self.settings())
        self.start()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "install",
            "start",
            "stop",
            "status",
            "supervise",
            "prepare-upgrade",
            "finish-upgrade",
            "rollback",
        ],
    )
    args = parser.parse_args()
    manager = Lifecycle()
    try:
        manager.guard()
        if args.action == "supervise":
            manager.supervise()
        else:
            with manager.lock():
                action = args.action
                if action == "status":
                    return 0 if manager.running() else 3
                if action == "prepare-upgrade":
                    manager.backup()
                elif action == "finish-upgrade":
                    manager.finish_upgrade()
                else:
                    getattr(manager, action.replace("-", "_"))()
        return 0
    except Exception as exc:
        # Do not print config values, credentials, upstream bodies or exception text.
        message = (
            "网易目录已启用，但固定版依赖缺失或损坏；请重新安装完整的网易整合预览包。"
            if isinstance(exc, NeteaseDependenciesMissing) else
            "音乐 Hub 生命周期失败（"
            + type(exc).__name__
            + "）；请检查配置、端口和预览包说明。"
        )
        logfile = os.environ.get("TRIM_TEMP_LOGFILE")
        if logfile:
            Path(logfile).write_text(message)
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
