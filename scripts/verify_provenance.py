#!/usr/bin/env python3
"""Check local provenance records, pinned references, digests and document links.

This intentionally does not claim to verify live upstreams or runtime behavior.
"""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def check_sha(value, label):
    check(isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value)), label)


def check_file_digest(path, expected):
    target = ROOT / path
    check(target.is_file(), f"Missing file: {path}")
    if target.is_file():
        check(hashlib.sha256(target.read_bytes()).hexdigest() == expected,
              f"SHA256 mismatch: {path}")


try:
    manifest = json.loads((ROOT / "SOURCE_VERSIONS.json").read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    sys.exit(f"Invalid manifest: {exc}")

check(manifest.get("schema_version") == 1, "Unsupported provenance schema")
check(manifest.get("repository") == "Surc/fnos_music_hub", "Wrong repository")
check_file_digest(manifest["design_archive"]["path"], manifest["design_archive"]["sha256"])
check_sha(manifest["legacy_project"]["observed_commit"], "Invalid legacy project SHA")
for source in manifest["legacy_project"]["upstreams"]:
    check_sha(source["adopted_commit_in_legacy"], f"Invalid legacy adopted SHA: {source['repository']}")
    if source.get("observed_commit"):
        check_sha(source["observed_commit"], f"Invalid legacy observation: {source['repository']}")

seen = set()
for source in manifest["sources"]:
    name = source["repository"]
    check(name not in seen, f"Duplicate source: {name}")
    seen.add(name)
    check_sha(source["observed_commit"], f"Invalid observed SHA: {name}")
    check(source.get("evidence_path") == manifest["design_archive"]["path"], f"Missing evidence: {name}")
    if source["adopted_commit"] is not None:
        check_sha(source["adopted_commit"], f"Invalid adopted SHA: {name}")
        check(bool(source.get("adoption_evidence")), f"Missing adoption evidence: {name}")
    if manifest["stage"] == "design-bootstrap":
        check(source["adopted_commit"] is None, f"Bootstrap must not claim code adoption: {name}")

skill = manifest["maintenance_skill"]
check(skill["name"] == "maintain-fnos-music-hub", "Wrong maintenance skill")
check(bool(re.fullmatch(r"\d+\.\d+\.\d+", skill["version"])), "Invalid skill version")
for path, digest in skill["files"].items():
    check_file_digest(path, digest)

for adapter in manifest.get("implemented_adapters", []):
    source = next((s for s in manifest["sources"] if s["repository"] == adapter["source_repository"]), None)
    check(source is not None and source["observed_commit"] == adapter["interface_commit"],
          f"Adapter pin differs from fixed source: {adapter['component']}")
    if source is not None and source["adopted_commit"] is not None:
        check(source["adopted_commit"] == adapter["interface_commit"],
              f"Adopted source differs from adapter pin: {adapter['component']}")
    for path in adapter["files"]:
        check((ROOT / path).is_file(), f"Missing adapter file: {path}")

schema_constants = [
    node.value.value
    for node in ast.parse((ROOT / "hub/store.py").read_text()).body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "DATABASE_SCHEMA" for target in node.targets)
    and isinstance(node.value, ast.Constant)
]
check(len(schema_constants) == 1, "Missing unique runtime DATABASE_SCHEMA constant")
if len(schema_constants) == 1:
    check(manifest["runtime_dependencies"]["database_schema"] == schema_constants[0],
          "Runtime database schema differs from source manifest")
    check(manifest["acceptance"]["qq_playlist_snapshots"]["database_schema"] == schema_constants[0],
          "Snapshot database schema differs from runtime")
qq_catalog = next(a for a in manifest["implemented_adapters"] if a["component"] == "QQ read-only catalog")
check(qq_catalog["full_playlist_export"] == manifest["acceptance"]["qq_accounts_and_catalog"]["full_playlist_export"],
      "QQ full playlist export capability records disagree")

optional = manifest.get("runtime_dependencies", {}).get("optional_qq")
if optional:
    check_file_digest(optional["lockfile"], optional["lockfile_sha256"])
    dependency = f"git+https://github.com/{optional['sdk_repository']}.git@{optional['sdk_commit']}"
    for path in (optional["lockfile"], "pyproject.toml"):
        check(dependency in (ROOT / path).read_text(), f"QQ dependency pin missing: {path}")

for evidence in (
    manifest.get("acceptance", {}).get("responsive_ui", {}),
    manifest.get("acceptance", {}).get("qq_accounts_and_catalog", {}),
    manifest.get("acceptance", {}).get("qq_playlist_snapshots", {}),
    manifest.get("acceptance", {}).get("qq_snapshot_recovery", {}),
    manifest.get("acceptance", {}).get("astra_review_hardening", {}),
):
    for path, digest in evidence.get("evidence_files_sha256", {}).items():
        check_file_digest(path, digest)

links = 0
for doc in ROOT.rglob("*.md"):
    if any(part in {".git", "node_modules", "build", "dist", ".pytest_cache", ".ruff_cache"}
           or part.startswith(".venv") for part in doc.relative_to(ROOT).parts):
        continue
    for match in re.finditer(r"\[[^\]]*\]\(([^\s)]+)\)", doc.read_text(encoding="utf-8")):
        link = match.group(1)
        parsed = urlsplit(link)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        links += 1
        target = (doc.parent / unquote(parsed.path)).resolve()
        check(target.is_relative_to(ROOT), f"Link escapes repository: {doc.relative_to(ROOT)}: {link}")
        check(target.exists(), f"Broken local link: {doc.relative_to(ROOT)}: {link}")

if errors:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    sys.exit(1)
print(f"PASS: {len(seen)} source observations, archive + skill digests, {links} local document links")
print("Scope: local provenance only; no live platform, application or FPK verification.")
