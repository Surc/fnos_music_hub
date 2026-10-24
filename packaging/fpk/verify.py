#!/usr/bin/env python3
"""Inspect the actual fnpack artifact, including every installed app byte and link."""

import argparse
import hashlib
import io
import json
import posixpath
import re
import tarfile
from pathlib import Path

from common import AUDIO, PINS, relative_path, sha256, write_json


def members(archive):
    result = {}
    for item in archive.getmembers():
        name = relative_path(item.name)
        if name in {"", "."} or item.isdir():
            continue
        if name in result or not (item.isfile() or item.issym() or item.islnk()):
            raise ValueError("duplicate or unsafe archive member")
        if item.issym():
            relative_path(
                posixpath.normpath(
                    posixpath.join(str(Path(name).parent), item.linkname)
                )
            )
        if item.islnk():
            relative_path(item.linkname)
        result[name] = item
    return result


def verify(path):
    with tarfile.open(path) as outer:
        entries = members(outer)
        manifest = outer.extractfile(entries["manifest"]).read().decode()
        fields = dict(re.findall(r"^\s*([\w_]+)\s*=\s*(.*?)\s*$", manifest, re.M))
        if (
            fields["appname"] != PINS["app_id"]
            or fields["version"] != PINS["package_version"]
        ):
            raise ValueError("wrong application/version")
        if "preview" not in fields["version"] or fields["platform"] != "x86":
            raise ValueError("not an amd64 preview package")
        payload = outer.extractfile(entries["app.tgz"]).read()
        if fields.get("checksum") != hashlib.md5(payload).hexdigest():
            raise ValueError("fnOS app.tgz MD5 mismatch")
        privilege = json.load(outer.extractfile(entries["config/privilege"]))
        if privilege != {
            "defaults": {"run-as": "package"},
            "username": PINS["app_id"],
            "groupname": PINS["app_id"],
        }:
            raise ValueError("wrong runtime identity")
        resource = json.load(outer.extractfile(entries["config/resource"]))
        if resource != {} or fields.get("install_dep_apps"):
            raise ValueError("unexpected external package/system resources")
        for script in (
            "main",
            "_dispatch",
            "install_init",
            "install_callback",
            "upgrade_init",
            "upgrade_callback",
            "uninstall_init",
            "uninstall_callback",
            "config_init",
            "config_callback",
        ):
            if entries[f"cmd/{script}"].mode & 0o111 == 0:
                raise ValueError("lifecycle script is not executable")
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as inner:
            content = members(inner)
            expected = json.load(inner.extractfile(content["CONTENTS.json"]))
            actual = {}
            for name, item in content.items():
                if name == "CONTENTS.json":
                    continue
                if Path(name).suffix.lower() in AUDIO or name.endswith(
                    (".sqlite3", ".db", ".log")
                ):
                    raise ValueError("audio/private runtime data in FPK")
                if item.issym():
                    actual[name] = {"link": item.linkname}
                else:
                    actual[name] = {
                        "sha256": hashlib.sha256(
                            inner.extractfile(item).read()
                        ).hexdigest(),
                        "mode": item.mode & 0o777,
                    }
            if actual != expected:
                raise ValueError("installed content differs from CONTENTS.json")
            bundle = json.load(inner.extractfile(content["bundle.json"]))
            if bundle["pins"] != PINS or bundle["real_nas_acceptance"] != "pending":
                raise ValueError("incorrect component/acceptance metadata")
    return {
        "schema": 1,
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "installed_files": len(actual),
        "bundle": bundle,
        "fpk_static_validation": "passed",
        "j4125_device_acceptance": "not_run",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fpk", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.fpk)
    if args.report:
        write_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False))
