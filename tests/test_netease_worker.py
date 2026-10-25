"""Real disposable subprocess lifecycle; synthetic stdin/stdout, no platform network."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from hub.errors import HubError
from modules.accounts.netease import NeteaseCredential
from modules.catalog.netease import NeteaseProtocol


@pytest.fixture
def workers(monkeypatch):
    original = asyncio.create_subprocess_exec
    processes, directories = [], []
    script = """
import json, sys, time
data = json.load(sys.stdin)
mode = data['operation']
if mode == 'oversize':
    sys.stdout.write('x' * (2 * 1024 * 1024 + 1))
    sys.stdout.flush()
    time.sleep(60)
elif mode == 'invalid_shape':
    print('[]')
elif mode == 'slow':
    time.sleep(60)
elif mode == 'invalid_json':
    print('synthetic-private-error')
else:
    time.sleep(0.05)
    print(json.dumps({'data': {'ok': True}}))
"""

    async def create(*args, **kwargs):
        assert args == (sys.executable, "-m", "modules.catalog.netease_worker")
        assert "synthetic-private-cookie" not in json.dumps(kwargs["env"])
        directory = Path(kwargs["env"]["XDG_CONFIG_HOME"]).parent
        assert directory.stat().st_mode & 0o777 == 0o700
        for key in (
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
            "XDG_RUNTIME_DIR",
        ):
            assert Path(kwargs["env"][key]).stat().st_mode & 0o777 == 0o700
        assert not any(
            k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
            for k in kwargs["env"]
        )
        directories.append(directory)
        process = await original(sys.executable, "-c", script, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(NeteaseProtocol, "available", staticmethod(lambda: True))
    return processes, directories


@pytest.mark.parametrize(
    "mode,code",
    [
        ("slow", "platform_unavailable"),
        ("cancel", None),
        ("oversize", "capacity_exceeded"),
        ("invalid_shape", "upstream_contract"),
        ("invalid_json", "upstream_contract"),
    ],
)
def test_worker_failures_reap_process_remove_xdg_and_release_slot(
    workers, monkeypatch, mode, code
):
    processes, directories = workers
    real_timeout = asyncio.timeout
    if mode == "slow":
        monkeypatch.setattr(asyncio, "timeout", lambda seconds: real_timeout(0.3))

    async def run():
        protocol = NeteaseProtocol()
        credential = NeteaseCredential('{"MUSIC_U":"synthetic-private-cookie"}')
        if mode == "cancel":
            task = asyncio.create_task(protocol.read(credential, "slow"))
            while not processes:
                await asyncio.sleep(0.005)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(HubError) as error:
                await protocol.read(credential, mode)
            assert error.value.code == code
            assert "synthetic-private" not in error.value.message
        assert all(p.returncode is not None for p in processes)
        for process in processes:
            with pytest.raises(ProcessLookupError):
                os.kill(process.pid, 0)
        assert all(not d.exists() for d in directories)
        assert await protocol.read(credential, "success") == {"ok": True}

    asyncio.run(run())
    assert all(not d.exists() for d in directories)


def test_worker_concurrency_is_bounded_with_unique_private_directories(
    workers, monkeypatch
):
    processes, directories = workers
    create = asyncio.create_subprocess_exec
    peak = 0

    async def counted(*args, **kwargs):
        nonlocal peak
        process = await create(*args, **kwargs)
        peak = max(peak, sum(p.returncode is None for p in processes))
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counted)

    async def run():
        protocol = NeteaseProtocol()
        results = await asyncio.gather(
            *[protocol.read(NeteaseCredential("{}"), "success") for _ in range(9)]
        )
        assert results == [{"ok": True}] * 9

    asyncio.run(run())
    assert 1 <= peak <= 4
    assert len(set(directories)) == len(directories) == 9
    assert all(p.returncode == 0 for p in processes)
    assert all(not d.exists() for d in directories)
