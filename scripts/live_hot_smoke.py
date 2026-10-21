"""Opt-in real Hot smoke test; output/audio must stay outside the repository.

This tests Hot + Hub adapters, not fnOS identity, NAS installation or cloud feedback.
"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from hub.config import Settings
from hub.domain import Principal, SubmitInput, make_manifest
from hub.store import Store
from hub.worker import Reconciler
from modules.catalog.hot import HotCatalog
from modules.download.hot import HotEngines

PIN = "07e86c3d06243cf1350925c0dd3be704005abd29"


async def run(args):
    source = Path(args.source).resolve()
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != PIN:
        raise RuntimeError(
            "Hot source checkout does not match the recorded adapter pin"
        )
    binary = source / "crates/hotdownloader-server/target/debug/hotdownloader-server"
    work = Path(tempfile.mkdtemp(prefix="hot-smoke-", dir=args.work_dir)).resolve()
    if work.is_relative_to(Path(__file__).resolve().parents[1]):
        raise RuntimeError("keep smoke-test audio outside the repository")
    root = work / "audio"
    root.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    os.environ["HUB_SMOKE_TOKEN"] = token
    env = {
        **os.environ,
        "HOTDOWNLOADER_DATA_DIR": str(work / "hot-data"),
        "HOTDOWNLOADER_DOWNLOAD_DIR": str(root),
        "HOTDOWNLOADER_BIND": f"127.0.0.1:{port}",
        "HOTDOWNLOADER_TOKEN": token,
        "HOTDOWNLOADER_LOG_LEVEL": "warn",
    }
    env.pop("AUTH_USERNAME", None)
    env.pop("AUTH_PASSWORD", None)
    origin = f"http://127.0.0.1:{port}"
    owner = Principal(instance_id="isolated-smoke-test", user_guid="smoke-user")
    cfg = Settings(
        instance_id=owner.instance_id,
        data_dir=work / "hub-data",
        bridge_url="http://127.0.0.1:1/api/v1",
        public_origin="http://localhost",
        secure_cookie=False,
        users={
            owner.user_guid: {
                "engine_url": origin,
                "engine_token_env": "HUB_SMOKE_TOKEN",
                "download_root": root,
            }
        },
    )
    report = {
        "scope": "real Hot HTTP + Hub catalog/outbox/audio validation; no fnOS auth",
        "source_commit": commit,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "keyword": args.keyword,
        "rid": args.rid,
        "quality": "320kmp3",
    }
    with (work / "engine.log").open("wb") as log:
        process = subprocess.Popen([str(binary)], env=env, stdout=log, stderr=log)
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                for _ in range(50):
                    try:
                        response = await client.get(origin + "/healthz", timeout=1)
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError("Hot exited; inspect engine.log")
                    await asyncio.sleep(0.2)
                else:
                    raise RuntimeError("Hot did not become ready")
            store, engines = Store(cfg.data_dir), HotEngines(cfg)
            snapshot = await engines.call(owner, "GET", "/api/settings")
            old = snapshot["settings"].get("autoDowngrade")
            await engines.call(
                owner,
                "PATCH",
                "/api/settings",
                {
                    "changes": {"autoDowngrade": False},
                    "expected": {"autoDowngrade": old},
                },
            )
            catalog = HotCatalog(engines, store)
            result = await catalog.search(owner, "kuwo", args.keyword)
            song = next(
                s for s in result["items"] if s.get("track", {}).get("id") == args.rid
            )
            report.update(
                search_count=len(result["items"]),
                found_title=song["title"],
                duration_expected=song["duration_seconds"],
            )
            from hub.domain import TrackRef

            full_song = store.song(owner, TrackRef.model_validate(song["track"]))
            manifest = make_manifest(owner, [full_song])
            request = SubmitInput(
                manifest_id=manifest["snapshot_id"], quality="320kmp3"
            )
            await engines.check_target(owner)
            task, _ = store.submit(
                owner, request, manifest, "smoke-download", engines.runtime_key(owner)
            )
            reconciler = Reconciler(store, engines)
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                await reconciler.tick()
                task = store._owned("tasks", owner.key, task["id"])
                if task["status"] in {"completed", "failed", "attention"}:
                    break
                await asyncio.sleep(1)
            report["task_status"] = task["status"]
            assets = store.owned_list("assets", owner)
            report["assets"] = [
                {
                    k: a[k]
                    for k in (
                        "track",
                        "bytes",
                        "sha256",
                        "codec",
                        "duration_seconds",
                        "bitrate",
                        "validation",
                        "index_status",
                    )
                }
                for a in assets
            ]
            report["errors"] = [e["error"] for e in task["entries"] if e["error"]]
        except Exception as exc:
            report["failure_class"] = type(exc).__name__
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    (work / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {"report_path": str(work / "report.json"), **report},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.get("task_status") == "completed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--keyword", default="DAYBREAK'S BELL")
    parser.add_argument("--rid", default="142276943")
    parser.add_argument("--timeout", type=int, default=120)
    sys.exit(asyncio.run(run(parser.parse_args())))
