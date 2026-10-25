#!/usr/bin/env python3
"""ONLINE build-machine step. Fetch pins, build portable tools, freeze offline inputs."""

import argparse
import gzip
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from common import HERE, PINS, ROOT, inventory, sha256, write_json
from wheelhouse import SDKS, describe, lock_digests, requirements


def run(command, *, cwd=None, env=None):
    subprocess.run(list(map(str, command)), cwd=cwd, env=env, check=True)


def download(pin, target):
    if not target.exists():
        temp = target.with_suffix(target.suffix + ".part")
        with (
            urllib.request.urlopen(pin["url"], timeout=60) as response,
            temp.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
        os.replace(temp, target)
    if sha256(target) != pin["sha256"]:
        raise ValueError(f"download digest mismatch: {target.name}")


def unpack(archive, dest, expected):
    if expected.exists():
        return
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")


def checkout(url, sha, path):
    if not path.exists():
        run(["git", "clone", url, path])
    run(["git", "checkout", "--detach", sha], cwd=path)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=path, text=True
    ).strip()
    if actual != sha or subprocess.check_output(["git", "diff", "HEAD"], cwd=path):
        raise ValueError("source is not the clean pinned commit")


def deterministic_tar(output, items, epoch):
    with (
        output.open("wb") as file,
        gzip.GzipFile(fileobj=file, mode="wb", filename="", mtime=epoch) as gz,
    ):
        with tarfile.open(fileobj=gz, mode="w") as tar:

            def normalize(info):
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = epoch
                return info

            for name, path in sorted(items.items()):
                tar.add(path, arcname=name, filter=normalize)


def source_copy(source, destination):
    # git's tracked bytes only, including pinned submodule source below.
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).split(b"\0")
    for item in filter(None, files):
        rel = Path(item.decode())
        path = source / rel
        if path.is_file():
            out = destination / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)


def wheel_sources(wheels, work, sources):
    """Retain matching PyPI sdists without executing their build/metadata hooks."""
    result = {}
    cache = work / "python-sources"
    cache.mkdir(exist_ok=True)
    sources.mkdir()
    for name, component in wheels.items():
        if name in SDKS:
            continue  # Exact tracked Git source is archived separately.
        version = component["version"]
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=60
        ) as response:
            metadata = json.load(response)
        candidates = [item for item in metadata["urls"] if item["packagetype"] == "sdist"]
        if len(candidates) != 1:
            raise ValueError(f"one matching source distribution required: {name}")
        item = candidates[0]
        filename = item["filename"]
        if Path(filename).name != filename:
            raise ValueError("invalid source distribution filename")
        pin = {"url": item["url"], "sha256": item["digests"]["sha256"]}
        download(pin, cache / filename)
        shutil.copyfile(cache / filename, sources / filename)
        result[name] = {"version": version, "file": filename, **pin}
    return result


def prepare(work, output, jobs):
    if output.exists():
        raise ValueError("output must not exist; work may be reused")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Linux x86_64 build machine required")
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)
    epoch = int(
        subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT)
    )
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch), "TZ": "UTC", "LC_ALL": "C"}
    sources = work / "corresponding-source"
    if sources.exists():
        shutil.rmtree(sources)
    sources.mkdir()
    downloads = {
        "python": "python.tar.gz",
        "musl": "musl-1.2.5.tar.gz",
        "ffmpeg": "ffmpeg-8.0.1.tar.xz",
        "fnpack": "fnpack",
    }
    for key, filename in downloads.items():
        download(PINS[key], work / filename)
    unpack(work / "python.tar.gz", work, work / "python")
    unpack(work / "musl-1.2.5.tar.gz", work, work / "musl-1.2.5")
    unpack(work / "ffmpeg-8.0.1.tar.xz", work, work / "ffmpeg-8.0.1")
    musl = work / "musl-1.2.5"
    prefix = work / "musl-install"
    run(["./configure", f"--prefix={prefix}", "--disable-shared"], cwd=musl, env=env)
    run(["make", f"-j{jobs}"], cwd=musl, env=env)
    run(["make", "install"], cwd=musl, env=env)
    cc = prefix / "bin/musl-gcc"
    ffmpeg = work / "ffmpeg-8.0.1"
    if (ffmpeg / "ffbuild/config.mak").exists():
        run(["make", "distclean"], cwd=ffmpeg, env=env)
    ffargs = [
        "./configure",
        f"--cc={cc}",
        "--host-cc=gcc",
        "--disable-everything",
        "--disable-autodetect",
        "--disable-x86asm",
        "--disable-doc",
        "--disable-debug",
        "--disable-network",
        "--disable-shared",
        "--enable-static",
        "--enable-ffmpeg",
        "--enable-ffprobe",
        "--enable-protocol=file,pipe",
        "--enable-demuxer=aac,flac,mp3,mov,ogg,wav",
        "--enable-decoder=aac,alac,flac,mp3,mp3float,opus,vorbis,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le",
        "--enable-parser=aac,flac,mpegaudio,opus,vorbis",
        "--enable-encoder=pcm_s16le",
        "--enable-muxer=null",
        "--enable-filter=anull,aresample,aformat,abuffer,abuffersink",
        "--enable-swresample",
        "--extra-cflags=-march=x86-64 -mtune=generic",
        "--extra-ldflags=-static",
    ]
    run(ffargs, cwd=ffmpeg, env=env)
    run(["make", f"-j{jobs}"], cwd=ffmpeg, env=env)
    hot = work / "HotDownloader"
    checkout("https://github.com/lerdb/HotDownloader.git", PINS["hot_commit"], hot)
    run(["git", "submodule", "update", "--init", "--recursive"], cwd=hot)
    sub = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=hot / "libs/um_crypto", text=True
    ).strip()
    if sub != PINS["hot_submodule"]:
        raise ValueError("Hot crypto submodule pin mismatch")
    run(
        ["rustup", "toolchain", "install", PINS["rust"], "--profile", "minimal"],
        env=env,
    )
    run(
        ["rustup", "target", "add", PINS["rust_target"], "--toolchain", PINS["rust"]],
        env=env,
    )
    rustflags = f"-C target-cpu=x86-64 -C target-feature=+crt-static --remap-path-prefix={work}=/build"
    sysroot = Path(
        subprocess.check_output(
            ["rustc", "+" + PINS["rust"], "--print", "sysroot"], text=True
        ).strip()
    )
    linker = sysroot / "lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-lld"
    if not linker.is_file():
        raise ValueError("fixed Rust toolchain rust-lld is missing")
    target_dir = work / "hot-musl-lld-target"
    rustenv = {
        **env,
        "RUSTFLAGS": rustflags,
        "CC_x86_64_unknown_linux_musl": str(cc),
        "CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER": str(linker),
        "CARGO_TARGET_DIR": str(target_dir),
    }
    run(
        [
            "cargo",
            "+" + PINS["rust"],
            "build",
            "--locked",
            "--release",
            "--target",
            PINS["rust_target"],
            "--manifest-path",
            "crates/hotdownloader-server/Cargo.toml",
            "-j",
            str(jobs),
        ],
        cwd=hot,
        env=rustenv,
    )
    qq = work / "QQMusicApi"
    checkout("https://github.com/L-1124/QQMusicApi.git", PINS["qq_commit"], qq)
    netease = work / "MusicBox"
    checkout("https://github.com/darknessomi/musicbox.git", PINS["netease_commit"], netease)
    python = work / "python/bin/python3"
    builder = work / "wheel-builder"
    if not builder.exists():
        run([python, "-m", "venv", builder])
    buildpy = builder / "bin/python"
    # Build backend version is explicit; never becomes a NAS build dependency.
    run([buildpy, "-m", "pip", "install", "hatchling==1.27.0"], env=env)
    wheels = output / "wheels"
    wheels.mkdir()
    runtime = [f"{name}=={version}" for name, version in sorted(requirements().items())]
    run(
        [
            buildpy,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--no-deps",
            "--dest",
            wheels,
            *runtime,
        ],
        env=env,
    )
    run(
        [
            buildpy,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            wheels,
            qq,
            netease,
        ],
        env=env,
    )
    wheel_manifest = describe(wheels)
    write_json(output / "wheelhouse.json", wheel_manifest)
    python_sources = wheel_sources(wheel_manifest, work, sources / "python-sdists")
    shutil.copytree(work / "python", output / "python", symlinks=True)
    for cache in list((output / "python").rglob("__pycache__")):
        shutil.rmtree(cache)
    (output / "bin").mkdir()
    binaries = {
        "ffmpeg": ffmpeg / "ffmpeg",
        "ffprobe": ffmpeg / "ffprobe",
        "hotdownloader-server": target_dir
        / PINS["rust_target"]
        / "release/hotdownloader-server",
    }
    for name, source in binaries.items():
        shutil.copy2(source, output / "bin" / name)
        os.chmod(output / "bin" / name, 0o755)
    shutil.copy2(work / "fnpack", output / "fnpack")
    os.chmod(output / "fnpack", 0o755)
    licenses = output / "licenses"
    licenses.mkdir()
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.txt"):
        shutil.copyfile(hot / name, licenses / ("HotDownloader-" + name))
        server_notice = hot / "crates/hotdownloader-server" / name
        if server_notice.exists():
            shutil.copyfile(server_notice, licenses / ("HotDownloader-server-" + name))
    for rel, name in (
        (hot / "libs/um_crypto/LICENSE_APACHE", "um_crypto-LICENSE_APACHE"),
        (hot / "libs/um_crypto/LICENSE_MIT", "um_crypto-LICENSE_MIT"),
        (qq / "LICENSE", "QQMusicApi-LICENSE"),
        (netease / "LICENSE", "MusicBox-LICENSE"),
        (musl / "COPYRIGHT", "musl-COPYRIGHT"),
        (ffmpeg / "COPYING.LGPLv2.1", "FFmpeg-COPYING.LGPLv2.1"),
        (ffmpeg / "LICENSE.md", "FFmpeg-LICENSE.md"),
    ):
        shutil.copyfile(rel, licenses / name)
    notices = []
    for source, label, pin in ((qq, "QQMusicApi", "qq_commit"), (netease, "MusicBox", "netease_commit")):
        notice = source / "NOTICE"
        if notice.is_file():
            shutil.copyfile(notice, licenses / (label + "-NOTICE"))
        notices.append(f"{label} commit {PINS[pin]}; upstream NOTICE: {'included' if notice.is_file() else 'not present'}; unmodified source included.\n")
    (licenses / "PYTHON-NOTICE.txt").write_text(
        "Fixed SDK and Python dependency distribution notice\n\n"
        + "".join(notices)
        + "Wheel LICENSE/NOTICE files remain in runtime/site-packages. "
        "Exact wheel metadata/hashes: wheelhouse.json. Matching PyPI sdists and SDK Git source "
        "are in the companion source archive; python-sources.json records their digests.\n"
    )
    source_copy(hot, sources / "HotDownloader")
    source_copy(hot / "libs/um_crypto", sources / "HotDownloader/libs/um_crypto")
    source_copy(qq, sources / "QQMusicApi")
    source_copy(netease, sources / "MusicBox")
    write_json(sources / "python-sources.json", python_sources)
    write_json(sources / "wheelhouse.json", wheel_manifest)
    for name in ("ffmpeg-8.0.1.tar.xz", "musl-1.2.5.tar.gz"):
        shutil.copyfile(work / name, sources / name)
    shutil.copytree(
        HERE, sources / "hub-packaging", ignore=shutil.ignore_patterns("__pycache__")
    )
    # Hub corresponding source, without private/untracked files and without Git metadata.
    source_copy(ROOT, sources / "fnos_music_hub")
    deterministic_tar(output / "sources.tar.gz", {"sources": sources}, epoch)
    write_json(
        output / "sources.json",
        {
            "companion": f"fnos-music-hub-{PINS['package_version']}-sources.tar.gz",
            "sha256": sha256(output / "sources.tar.gz"),
            "sources": {
                "HotDownloader": PINS["hot_commit"],
                "um_crypto": PINS["hot_submodule"],
                "QQMusicApi": PINS["qq_commit"],
                "MusicBox": PINS["netease_commit"],
                "python_sdists": python_sources,
                "ffmpeg": PINS["ffmpeg"],
                "musl": PINS["musl"],
                "python": PINS["python"],
            },
            "instructions": "See hub-packaging/README.md; all runtime source patches: none.",
        },
    )
    write_json(
        output / "inputs.json",
        {
            "schema": 1,
            "pins": PINS,
            "runtime_locks": lock_digests(),
            "content": inventory(output, ("inputs.json",)),
            "build_environment": {
                "os": platform.platform(),
                "gcc": subprocess.check_output(
                    ["gcc", "--version"], text=True
                ).splitlines()[0],
                "rustc": subprocess.check_output(
                    ["rustc", "+" + PINS["rust"], "--version"], text=True
                ).strip(),
                "ffmpeg_configure": ffargs,
                "rustflags": rustflags,
                "source_date_epoch": epoch,
                "hub_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        sys.exit("jobs must be 1..32")
    prepare(args.work.resolve(), args.output.resolve(), args.jobs)
