#!/usr/bin/env python3
"""Offline assembly from a verified input closure; never downloads or compiles."""

import argparse
import base64
import csv
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tarfile
import zlib
from pathlib import Path

from common import (
    HERE,
    PINS,
    ROOT,
    audit_elf,
    inventory,
    no_user_data,
    sha256,
    write_json,
)
from fetch_inputs import deterministic_tar, source_copy


def normalize_installed_metadata(site):
    # Runtime uses python -m, never pip-generated scripts with a staging-path shebang.
    shutil.rmtree(site / "bin", ignore_errors=True)
    for direct in site.glob("*.dist-info/direct_url.json"):
        direct.unlink()
    for record in site.glob("*.dist-info/RECORD"):
        rows = list(csv.reader(record.read_text().splitlines()))
        updated = []
        for name, _, _ in rows:
            file = (site / name).resolve()
            if (
                file == record
                or not file.is_relative_to(site.resolve())
                or not file.is_file()
            ):
                continue
            value = (
                base64.urlsafe_b64encode(hashlib.sha256(file.read_bytes()).digest())
                .rstrip(b"=")
                .decode()
            )
            updated.append((name, "sha256=" + value, str(file.stat().st_size)))
        updated.append((record.relative_to(site).as_posix(), "", ""))
        with record.open("w", newline="") as output:
            csv.writer(output, lineterminator="\n").writerows(sorted(updated))


def icon(size):
    def chunk(kind, value):
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value))
        )

    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            # Deterministic opaque music glyph; no external design/tool dependency.
            u, v = x / size, y / size
            ink = (
                (0.50 < u < 0.58 and 0.24 < v < 0.68)
                or (0.55 < u < 0.78 and 0.22 < v < 0.31)
                or (((u - 0.44) / 0.14) ** 2 + ((v - 0.69) / 0.10) ** 2 < 1)
            )
            raw.extend((241, 251, 248) if ink else (22, 106, 97))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def assemble(inputs, output):
    recorded = json.loads((inputs / "inputs.json").read_text())
    if recorded["pins"] != PINS:
        raise ValueError("input versions do not match committed pins")
    if inventory(inputs, ("inputs.json",)) != recorded["content"]:
        raise ValueError("input closure hash/path/mode mismatch")
    if output.exists():
        raise ValueError("output must not exist")
    subprocess.run(
        ["git", "diff", "--exit-code", "HEAD"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT
    ):
        raise ValueError("commit source changes before producing a candidate")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    epoch = int(
        subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT)
    )
    shutil.copytree(HERE / "template", output)
    app = output / "app"
    shutil.copytree(inputs / "python", app / "runtime/python", symlinks=True)
    # Hub never uses deprecated crypt(3); avoid an extra OS libcrypt.so.1 dependency.
    for extension in (app / "runtime/python/lib/python3.12/lib-dynload").glob(
        "_crypt.*.so"
    ):
        extension.unlink()
    (app / "runtime/site-packages").mkdir(parents=True)
    (app / "bin").mkdir()
    for binary in ("hotdownloader-server", "ffmpeg", "ffprobe"):
        shutil.copy2(inputs / "bin" / binary, app / "bin" / binary)
        os.chmod(app / "bin" / binary, 0o755)
    wheels = sorted((inputs / "wheels").glob("*.whl"))
    if not wheels:
        raise ValueError("missing wheels")
    python = app / "runtime/python/bin/python3"
    env = {
        **os.environ,
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--no-compile",
            "--target",
            str(app / "runtime/site-packages"),
            *map(str, wheels),
        ],
        env=env,
        check=True,
    )
    env["PYTHONPATH"] = str(app / "runtime/site-packages")
    subprocess.run([str(python), "-m", "pip", "check"], env=env, check=True)
    normalize_installed_metadata(app / "runtime/site-packages")
    # Narrow tracked-source allowlist: no whole checkout/runtime directory copy.
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    for entry in filter(None, files):
        rel = Path(entry.decode())
        is_python = rel.parts[0] in {"hub", "modules", "apps"} and rel.suffix == ".py"
        is_web = rel.parent == Path("apps/web") and rel.suffix in {
            ".html",
            ".css",
            ".js",
        }
        if is_python or is_web or rel == Path("scripts/run_hot_user.py"):
            dest = app / "server" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
    shutil.copytree(
        HERE / "native", app / "native", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(inputs / "licenses", app / "licenses")
    for name in (
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "requirements.lock",
        "requirements-qq.lock",
    ):
        shutil.copyfile(ROOT / name, app / "licenses" / name)
    shutil.copyfile(HERE / "README.md", app / "licenses/FPK-BUILD.md")
    shutil.copyfile(HERE / "versions.json", app / "licenses/versions.json")
    # Reuse frozen components across Hub commits; regenerate matching Hub sources offline.
    source_work = output.parent / "source-work"
    source_work.mkdir()
    with tarfile.open(inputs / "sources.tar.gz") as archive:
        archive.extractall(source_work, filter="data")
    sources = source_work / "sources"
    for name in ("fnos_music_hub", "hub-packaging"):
        shutil.rmtree(sources / name)
    source_copy(ROOT, sources / "fnos_music_hub")
    shutil.copytree(
        HERE, sources / "hub-packaging", ignore=shutil.ignore_patterns("__pycache__")
    )
    companion = (
        output.parent / f"fnos-music-hub-{PINS['package_version']}-sources.tar.gz"
    )
    deterministic_tar(companion, {"sources": sources}, epoch)
    source_metadata = json.loads((inputs / "sources.json").read_text())
    source_metadata.update({"sha256": sha256(companion), "hub_commit": commit})
    write_json(app / "licenses/sources.json", source_metadata)
    shutil.rmtree(source_work)
    (app / "ui/images").mkdir()
    for size, filename in ((64, "ICON.PNG"), (256, "ICON_256.PNG")):
        data = icon(size)
        (output / filename).write_bytes(data)
        (app / f"ui/images/icon_{size}.png").write_bytes(data)
    (app / "ui/launch.html").write_text(
        "<!doctype html><meta charset=utf-8><p>请完成安装向导。</p>"
    )
    # Remove only build caches from trusted inputs, never copy user configuration.
    for path in list(app.rglob("__pycache__")):
        shutil.rmtree(path)
    for path in app.rglob("*.pyc"):
        path.unlink()
    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            os.chmod(path, 0o755 if path.stat().st_mode & 0o111 else 0o644)
    for path in (output / "cmd").iterdir():
        os.chmod(path, 0o755)
    os.chmod(app / "ui/index.cgi", 0o755)
    no_user_data(output)
    compatibility = audit_elf(app)
    bundle = {
        "schema": 1,
        "package_version": PINS["package_version"],
        "hub_version": PINS["hub_version"],
        "hub_commit": commit,
        "source_date_epoch": epoch,
        "pins": PINS,
        "inputs_sha256": sha256(inputs / "inputs.json"),
        "compatibility": compatibility,
        "build_environment": recorded["build_environment"],
        "real_nas_acceptance": "pending",
        "release": False,
        "excluded_stdlib_extensions": [
            "_crypt (unused; avoids external libcrypt.so.1)"
        ],
    }
    write_json(app / "bundle.json", bundle)
    contents = inventory(app, ("CONTENTS.json",))
    # fnpack appends these declarations to app.tgz. Include their expected bytes,
    # but never place physical duplicates in app/ before calling the official tool.
    for name in ("privilege", "resource"):
        contents["config/" + name] = {
            "sha256": sha256(output / "config" / name),
            "mode": 0o644,
        }
    write_json(app / "CONTENTS.json", contents)
    for path in [*output.rglob("*"), output]:
        os.utime(path, (epoch, epoch), follow_symlinks=False)
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            assemble(args.inputs.resolve(), args.output.resolve()), ensure_ascii=False
        )
    )
