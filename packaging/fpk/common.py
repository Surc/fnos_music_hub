"""Build-side integrity helpers; all paths and subprocesses are explicit."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PINS = json.loads((HERE / "versions.json").read_text())
AUDIO = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac"}


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    )


def inventory(root, exclude=()):
    result = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel in exclude:
            continue
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise ValueError(f"external symlink: {rel}")
            result[rel] = {"link": os.readlink(path)}
        elif path.is_file():
            result[rel] = {"sha256": sha256(path), "mode": path.stat().st_mode & 0o777}
        elif not path.is_dir():
            raise ValueError(f"special file: {rel}")
    return result


def relative_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe archive path")
    return path.as_posix().removeprefix("./")


def audit_elf(root):
    report = {"elf_count": 0, "required_glibc": "0.0", "needed": []}
    available = {p.name for p in root.rglob("*") if p.is_file()}
    system = {
        "libc.so.6",
        "libm.so.6",
        "libpthread.so.0",
        "libdl.so.2",
        "librt.so.1",
        "libutil.so.1",
        "ld-linux-x86-64.so.2",
        "libgcc_s.so.1",
    }
    maximum = (0, 0)
    needed_all = set()
    for file in sorted(root.rglob("*")):
        if file.is_symlink() or not file.is_file():
            continue
        with file.open("rb") as stream:
            header = stream.read(20)
        if not header.startswith(b"\x7fELF"):
            continue
        if header[4:6] != b"\x02\x01" or header[18:20] != b"\x3e\x00":
            raise ValueError("ELF must be little-endian Linux x86_64")
        report["elf_count"] += 1
        dynamic = subprocess.check_output(["readelf", "-d", str(file)], text=True)
        needed = set(re.findall(r"Shared library: \[(.*?)\]", dynamic))
        for dependency in list(needed):
            if "/" in dependency:
                resolved = Path(
                    dependency.replace("$ORIGIN", str(file.parent))
                ).resolve()
                if (
                    not resolved.is_relative_to(root.resolve())
                    or not resolved.is_file()
                ):
                    raise ValueError("ELF dependency escapes bundle")
                needed.remove(dependency)
                needed.add(resolved.name)
        if not needed <= available | system:
            raise ValueError(
                f"unbundled ELF libraries: {sorted(needed - available - system)}"
            )
        needed_all |= needed
        versions = subprocess.check_output(["readelf", "-V", str(file)], text=True)
        for major, minor in re.findall(r"GLIBC_(\d+)\.(\d+)", versions):
            maximum = max(maximum, (int(major), int(minor)))
        notes = subprocess.check_output(["readelf", "-n", str(file)], text=True)
        if re.search(r"x86-64-v[234]", notes):
            raise ValueError("ELF declares CPU above J4125 baseline")
        if file.parent == root / "bin" and file.name in {
            "ffmpeg",
            "ffprobe",
            "hotdownloader-server",
        }:
            headers = subprocess.check_output(["readelf", "-l", str(file)], text=True)
            if needed or "INTERP" in headers:
                raise ValueError("Hot and media tools must be static musl executables")
    report["required_glibc"] = ".".join(map(str, maximum))
    report["needed"] = sorted(needed_all)
    if maximum > tuple(map(int, PINS["glibc_max"].split("."))):
        raise ValueError(f"GLIBC {maximum} exceeds preview build ceiling")
    if report["elf_count"] < 4:
        raise ValueError("incomplete native payload")
    return report


def no_user_data(root):
    for file in root.rglob("*"):
        name = file.name.lower()
        if file.suffix.lower() in AUDIO or name.endswith((".db", ".sqlite3", ".log")):
            raise ValueError(f"runtime data/audio in package: {file.relative_to(root)}")
        if name in {
            "hub.json",
            "secrets.json",
            "vault.key",
            "settings.json",
            "credentials.json",
        }:
            raise ValueError("private configuration in payload")
        if name in {".git", "node_modules", "__pycache__"}:
            raise ValueError("development/runtime cache in payload")
