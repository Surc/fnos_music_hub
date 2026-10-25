"""Pinned runtime closure and an auditable manifest for offline Python inputs."""

import email
import re
import zipfile

from common import PINS, ROOT, sha256

LOCKS = ("requirements.lock", "requirements-qq.lock", "requirements-netease.lock")
SDKS = {
    "qqmusic-api-python": ("L-1124/QQMusicApi", "qq_commit", "0.8.2"),
    "netease-musicbox": ("darknessomi/musicbox", "netease_commit", "0.5.3"),
}


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def requirements(root=ROOT):
    """Reject unlocked or conflicting lines; the SDK wheels come from fixed Git SHAs."""
    result = {}
    for lock in LOCKS:
        for line in (root / lock).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line == "-r requirements.lock":
                continue
            if " @ " in line:
                name, url = line.split(" @ ", 1)
                key = normalized(name)
                if key not in SDKS:
                    raise ValueError("unrecognized SDK requirement")
                repo, pin, _ = SDKS[key]
                if url != f"git+https://github.com/{repo}.git@{PINS[pin]}":
                    raise ValueError("SDK lock differs from component pin")
                continue
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
            if not match:
                raise ValueError("runtime requirement must be exactly pinned")
            name, version = match.groups()
            key = normalized(name)
            if key in result and result[key] != version:
                raise ValueError("conflicting runtime requirement")
            result[key] = version
    return result


def lock_digests(root=ROOT):
    return {name: sha256(root / name) for name in LOCKS}


def describe(wheels, root=ROOT):
    expected = requirements(root)
    expected.update({name: entry[2] for name, entry in SDKS.items()})
    result = {}
    for wheel in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise ValueError("wheel must contain one distribution")
            info = email.message_from_bytes(archive.read(metadata[0]))
            name = normalized(info["Name"])
            if name in result or expected.get(name) != info["Version"]:
                raise ValueError("unexpected, duplicate or incorrectly versioned wheel")
            licenses = [
                n for n in archive.namelist()
                if not n.endswith("/") and any(
                    part.lower().startswith(("license", "licence", "copying", "notice"))
                    for part in n.split("/")[1:]
                )
            ]
            if not licenses:
                raise ValueError(f"wheel missing license: {name}")
            result[name] = {
                "version": info["Version"],
                "wheel": wheel.name,
                "sha256": sha256(wheel),
                "requires_dist": info.get_all("Requires-Dist", []),
                "license_files": sorted(licenses),
                "source_commit": PINS[SDKS[name][1]] if name in SDKS else None,
            }
    if result.keys() != expected.keys():
        raise ValueError("wheelhouse does not cover the complete runtime locks")
    return result
