#!/usr/bin/env python3
"""Disposable Linux integration: real bundled Hub/Hot; synthetic users, no music API."""

import argparse
import importlib.util
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from common import sha256, write_json


def smoke(stage, report, require):
    if (
        os.getuid() == 0
        or int(Path("/proc/self/stat").read_text().split()[0]) != os.getpid()
    ):
        write_json(
            report,
            {
                "status": "blocked",
                "reason": "non-root and matching Linux procfs required",
                "real_nas_acceptance": "not_run",
            },
        )
        if require:
            raise RuntimeError("native smoke requires ordinary non-root Linux")
        return
    with tempfile.TemporaryDirectory(prefix="hub-fpk-smoke-") as directory:
        root = Path(directory)
        program = root / "program"
        shutil.copytree(stage / "app", program, symlinks=True)
        var = root / "var"
        env = {
            **os.environ,
            "TRIM_APPDEST": str(program),
            "TRIM_PKGVAR": str(var),
            "wizard_public_origin": "https://native-smoke.test",
            "wizard_bridge_url": "http://127.0.0.1:9/api/v1",
            "TRIM_TEMP_LOGFILE": str(root / "fnos-error.txt"),
        }
        os.environ.update(
            {
                key: value
                for key, value in env.items()
                if key.startswith(("TRIM_", "wizard_"))
            }
        )
        spec = importlib.util.spec_from_file_location(
            "native_smoke_service", program / "native/service.py"
        )
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        manager = native.Lifecycle(program)
        manager.guard()
        manager.install()
        cfg = native.read_json(manager.config / "hub.json")
        assert cfg["netease_enabled"] is False and cfg["qq_accounts_enabled"] is False
        cfg["users"] = {
            "synthetic-a": {
                "engine_url": "http://127.0.0.1:28787",
                "engine_token_env": "HUB_HOT_A",
                "download_root": str(var / "downloads/a"),
            },
            "synthetic-b": {
                "engine_url": "http://127.0.0.1:28788",
                "engine_token_env": "HUB_HOT_B",
                "download_root": str(var / "downloads/b"),
            },
        }
        native.atomic_json(manager.config / "hub.json", cfg)
        try:
            manager.start()
            before = manager.records()
            assert len(before["children"]) == 3 and manager.running()
            manager.start()
            assert manager.records() == before
            values = native.read_json(manager.config / "secrets.json")
            assert values["HUB_HOT_A"] != values["HUB_HOT_B"]
            for item, own, other in zip(
                before["children"][:2], ("A", "B"), ("B", "A"), strict=True
            ):
                environ = Path(f"/proc/{item['pid']}/environ").read_bytes()
                assert values[f"HUB_HOT_{own}"].encode() in environ
                assert values[f"HUB_HOT_{other}"].encode() not in environ
            native.send_signal(before["children"][0], signal.SIGTERM)
            deadline = time.monotonic() + 15
            while (
                any(native.alive(p) for p in before["children"])
                and time.monotonic() < deadline
            ):
                time.sleep(0.1)
            assert not any(native.alive(p) for p in before["children"])
            # Kernel route lookup only: connect on UDP does not send a packet.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("192.0.2.1", 9))
                lan_ip = probe.getsockname()[0]
            cfg.update(
                public_origin=f"http://{lan_ip}:8790",
                lan_http_test=True,
                secure_cookie=False,
            )
            native.atomic_json(manager.config / "hub.json", cfg)
            manager.launch_page(manager.settings())
            manager.start()
            assert manager.running()
            assert native.get_json(f"http://{lan_ip}:8790/healthz")["status"] == "ok"
            hub_pid = manager.records()["children"][-1]["pid"]
            command = Path(f"/proc/{hub_pid}/cmdline").read_bytes().split(b"\0")
            assert command[command.index(b"--host") + 1] == lan_ip.encode()
            manager.stop()
            # Return to HTTPS defaults for the existing upgrade/rollback coverage.
            cfg.update(
                public_origin="https://native-smoke.test",
                lan_http_test=False,
                secure_cookie=True,
            )
            # Both SDKs enabled against actual packaged dependencies, without an account.
            cfg.update(netease_enabled=True, qq_accounts_enabled=True)
            native.atomic_json(manager.config / "hub.json", cfg)
            manager.start()
            manager.stop()
            requests = program / "runtime/site-packages/requests"
            missing = root / "masked-requests"
            requests.rename(missing)
            try:
                result = subprocess.run(
                    [str(stage / "cmd/main"), "start"], env=env, timeout=60
                )
                assert result.returncode != 0 and not manager.running()
                assert (
                    "网易目录已启用，但固定版依赖缺失或损坏"
                    in Path(env["TRIM_TEMP_LOGFILE"]).read_text()
                )
                cfg["netease_enabled"] = False
                native.atomic_json(manager.config / "hub.json", cfg)
                manager.start()  # Missing optional dependency does not break QQ/Kuwo mode.
                assert manager.running()
                manager.stop()
            finally:
                missing.rename(requests)
            cfg["netease_enabled"] = True
            native.atomic_json(manager.config / "hub.json", cfg)
            manager.start()
            snapshot = manager.backup()
            assert manager.validated_snapshot() == snapshot
            # Break only the disposable NEW app; the backup retains old executable bytes.
            (program / "server/hub/__main__.py").write_text(
                "raise RuntimeError('synthetic upgrade failure')\n"
            )
            result = subprocess.run(
                [str(stage / "cmd/upgrade_callback")], env=env, timeout=90
            )
            assert result.returncode != 0
            old = native.Lifecycle(snapshot / "program")
            assert old.running() and manager.active.resolve() == snapshot / "program"
            db, key = var / "state/hub.sqlite3", var / "state/vault.key"
            hashes = (sha256(db), sha256(key))
            result = subprocess.run(
                [str(stage / "cmd/uninstall_init")], env=env, timeout=90
            )
            assert result.returncode == 0
            result = subprocess.run(
                [str(stage / "cmd/uninstall_callback")], env=env, timeout=10
            )
            assert result.returncode == 0 and (sha256(db), sha256(key)) == hashes
            assert not old.running()
            write_json(
                report,
                {
                    "status": "passed",
                    "real_nas_acceptance": "not_run",
                    "scope": "ordinary Linux, bundled services, synthetic users, no platform login/download",
                    "checks": [
                        "start/health",
                        "idempotent start",
                        "two Hot token isolation",
                        "NetEase and QQ default disabled",
                        "enabled NetEase crypto/native dependencies and QQ coexist",
                        "missing NetEase transitive dependency gives explicit startup error",
                        "disabled NetEase tolerates missing optional dependency with dual Hot/QQ",
                        "child exit stops all",
                        "explicit LAN HTTP binds selected RFC1918 interface with real bundled Hub/Hot",
                        "backup integrity",
                        "failed upgrade shell rollback",
                        "old program and database/key recovery",
                        "uninstall retains state",
                    ],
                },
            )
        finally:
            manager.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--require", action="store_true")
    args = parser.parse_args()
    smoke(args.stage.resolve(), args.report.resolve(), args.require)
