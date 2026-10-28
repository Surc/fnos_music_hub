"""Lifecycle/data invariants, using disposable state and synthetic identities only."""

import importlib.util
import io
import json
import os
import signal
import socket
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

FPK = Path(__file__).resolve().parents[1] / "packaging/fpk"
sys.path.insert(0, str(FPK))
import common  # noqa: E402
import prepare  # noqa: E402
import verify  # noqa: E402
import wheelhouse  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "native_service", FPK / "native/service.py"
)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


@pytest.fixture
def manager(tmp_path, monkeypatch):
    program, var = tmp_path / "program", tmp_path / "var"
    (program / "ui").mkdir(parents=True)
    (program / "bundle.json").write_text('{"package_version":"0.1.0-preview.1"}')
    (program / "code").write_text("old-program")
    monkeypatch.setenv("TRIM_APPDEST", str(program))
    monkeypatch.setenv("TRIM_PKGVAR", str(var))
    monkeypatch.setenv("wizard_public_origin", "https://music.test")
    monkeypatch.setenv("wizard_bridge_url", "http://127.0.0.1:18090/yinqiao/v1")
    value = native.Lifecycle(program)
    for path in (value.var, value.config, value.state, value.run):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    value.install()
    return value


def set_users(manager):
    cfg = native.read_json(manager.config / "hub.json")
    cfg["users"] = {
        "synthetic-a": {
            "engine_url": "http://127.0.0.1:18787",
            "engine_token_env": "HUB_HOT_A",
            "download_root": str(manager.var / "downloads/a"),
        },
        "synthetic-b": {
            "engine_url": "http://127.0.0.1:18788",
            "engine_token_env": "HUB_HOT_B",
            "download_root": str(manager.var / "downloads/b"),
        },
    }
    native.atomic_json(manager.config / "hub.json", cfg)
    return cfg


def test_registry_removed_during_status_is_stopped(manager, monkeypatch):
    native.atomic_json(manager.registry, {"ready": True})
    original_read = native.read_json

    def supervisor_exit(path):
        if path == manager.registry:
            path.unlink(missing_ok=True)
        return original_read(path)

    monkeypatch.setattr(native, "read_json", supervisor_exit)
    assert manager.records() == {}
    assert manager.running() is False


def test_install_is_idempotent_and_launch_has_no_secrets(manager, monkeypatch):
    assert native.read_json(manager.config / "hub.json")["netease_enabled"] is False
    old = (manager.config / "hub.json").read_bytes()
    monkeypatch.setenv("wizard_public_origin", "https://other.test")
    manager.install()
    assert (manager.config / "hub.json").read_bytes() == old
    assert (manager.config / "hub.json").stat().st_mode & 0o777 == 0o600
    assert "music.test" in (manager.target / "ui/launch.html").read_text()
    assert "instance_id" not in (manager.target / "ui/launch.html").read_text()


def test_explicit_lan_install_binds_selected_interface_and_preserves_config(
    manager, monkeypatch
):
    (manager.config / "hub.json").unlink()
    monkeypatch.setenv("wizard_access_mode", "lan_http_test")
    monkeypatch.setenv("wizard_public_origin", "http://192.168.1.6:8790/")
    manager.install()
    cfg = manager.settings()
    assert cfg.lan_http_test and not cfg.secure_cookie
    assert manager.hub_host(cfg) == "192.168.1.6"
    assert "明文" in (manager.target / "ui/launch.html").read_text()
    before = (manager.config / "hub.json").read_bytes()
    monkeypatch.setenv("wizard_access_mode", "https")
    manager.install()
    assert (manager.config / "hub.json").read_bytes() == before


@pytest.mark.parametrize(
    "mode,origin",
    [
        ("https", "http://192.168.1.6:8790"),
        ("typo", "https://music.test"),
        ("lan_http_test", "https://music.test"),
        ("lan_http_test", "http://192.168.1.6:9999"),
        ("lan_http_test", "http://8.8.8.8:8790"),
    ],
)
def test_install_rejects_invalid_mode_or_origin_without_persisting(
    manager, monkeypatch, mode, origin
):
    (manager.config / "hub.json").unlink()
    monkeypatch.setenv("wizard_access_mode", mode)
    monkeypatch.setenv("wizard_public_origin", origin)
    with pytest.raises((ValueError, RuntimeError)):
        manager.install()
    assert not (manager.config / "hub.json").exists()


def test_lan_ports_and_health_keep_hot_on_loopback(manager, monkeypatch):
    cfg = set_users(manager)
    cfg.update(
        public_origin="http://192.168.1.6:8790", lan_http_test=True, secure_cookie=False
    )
    native.atomic_json(manager.config / "hub.json", cfg)
    cfg = manager.settings()
    bound = []

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def setsockopt(self, *args):
            pass

        def bind(self, address):
            bound.append(address)

    monkeypatch.setattr(native.socket, "socket", Probe)
    manager.check_ports(cfg)
    assert bound == [("192.168.1.6", 8790), ("127.0.0.1", 18787), ("127.0.0.1", 18788)]
    calls = []

    def health(url, **kwargs):
        calls.append((url, kwargs))
        return {"status": "ok", "version": "0.1.0a1"}

    monkeypatch.setattr(native, "get_json", health)
    # A health probe with no users must reach the selected LAN interface, not loopback.
    assert manager.health(cfg.model_copy(update={"users": {}}), {})
    assert calls == [("http://192.168.1.6:8790/healthz", {"host": "192.168.1.6:8790"})]


@pytest.mark.parametrize("enabled", [False, True])
def test_preflight_only_probes_enabled_netease_and_reports_missing_dependency(
    manager, monkeypatch, enabled
):
    cfg = native.read_json(manager.config / "hub.json")
    cfg["netease_enabled"] = enabled
    native.atomic_json(manager.config / "hub.json", cfg)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "--netease" in command:
            assert kwargs["timeout"] == 20
            assert kwargs["stderr"] == subprocess.DEVNULL
            raise subprocess.CalledProcessError(1, command, stderr="synthetic-secret")

    monkeypatch.setattr(native.subprocess, "run", run)
    if enabled:
        with pytest.raises(native.NeteaseDependenciesMissing) as error:
            manager.preflight()
        assert "synthetic-secret" not in str(error.value)
    else:
        assert manager.preflight().netease_enabled is False
        assert len(calls) == 3  # Core/QQ and media only; no NEMbox import.


def test_runtime_locks_deduplicate_shared_pins_and_reject_drift(tmp_path):
    for lock in wheelhouse.LOCKS:
        (tmp_path / lock).write_bytes((common.ROOT / lock).read_bytes())
    deps = wheelhouse.requirements(tmp_path)
    assert deps["requests"] == "2.34.2" and deps["charset-normalizer"] == "3.5.2"
    path = tmp_path / "requirements-netease.lock"
    path.write_text(path.read_text() + "charset-normalizer==1.0.0\n")
    with pytest.raises(ValueError, match="conflicting"):
        wheelhouse.requirements(tmp_path)
    path.write_text("requests>=2\n")
    with pytest.raises(ValueError, match="exactly pinned"):
        wheelhouse.requirements(tmp_path)


def test_offline_assembly_rejects_stale_runtime_lock_before_tools(
    tmp_path, monkeypatch
):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    common.write_json(
        inputs / "inputs.json",
        {
            "pins": common.PINS,
            "content": {},
            "runtime_locks": {},
        },
    )
    monkeypatch.setattr(
        prepare.subprocess, "run", lambda *a, **kw: pytest.fail("tool started")
    )
    with pytest.raises(ValueError, match="runtime locks"):
        prepare.assemble(inputs, tmp_path / "output")


@pytest.mark.parametrize("fault", ["missing", "version", "license", "duplicate"])
def test_wheel_manifest_rejects_incomplete_or_unlicensed_inputs(
    tmp_path, monkeypatch, fault
):
    monkeypatch.setattr(
        wheelhouse, "requirements", lambda root: {"example": "1", "other": "2"}
    )
    monkeypatch.setattr(wheelhouse, "SDKS", {})

    def wheel(filename, name, version, license=True):
        with zipfile.ZipFile(tmp_path / filename, "w") as archive:
            archive.writestr(
                f"{name}.dist-info/METADATA", f"Name: {name}\nVersion: {version}\n"
            )
            if license:
                archive.writestr(
                    f"{name}.dist-info/licenses/LICENSE", "synthetic-license"
                )

    wheel(
        "example.whl", "example", "0" if fault == "version" else "1", fault != "license"
    )
    if fault != "missing":
        wheel("other.whl", "other", "2")
    if fault == "duplicate":
        wheel("duplicate.whl", "example", "1")
    with pytest.raises(ValueError):
        wheelhouse.describe(tmp_path)


def test_rapidfuzz_wheel_rejects_hidden_native_runtime_requirement(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        wheelhouse, "requirements", lambda root: {"rapidfuzz": "3.14.6"}
    )
    monkeypatch.setattr(wheelhouse, "SDKS", {})
    with zipfile.ZipFile(
        tmp_path / "rapidfuzz-3.14.6-py3-none-any.whl", "w"
    ) as archive:
        archive.writestr(
            "rapidfuzz.dist-info/METADATA", "Name: RapidFuzz\nVersion: 3.14.6\n"
        )
        archive.writestr("rapidfuzz.dist-info/licenses/LICENSE", "synthetic-license")
        archive.writestr("rapidfuzz/native.so", b"synthetic-native-library")
    with pytest.raises(ValueError, match="pure Python"):
        wheelhouse.describe(tmp_path)


def test_missing_config_with_existing_database_refuses_new_instance(manager):
    (manager.state / "hub.sqlite3").write_bytes(b"synthetic-existing-db")
    (manager.config / "hub.json").unlink()
    with pytest.raises(RuntimeError, match="restore_matching_config"):
        manager.install()
    assert (manager.state / "hub.sqlite3").read_bytes() == b"synthetic-existing-db"


def test_private_hot_tokens_remain_distinct_and_stable(manager):
    set_users(manager)
    cfg = manager.settings()
    first = manager.secrets(cfg)
    assert first["HUB_HOT_A"] != first["HUB_HOT_B"]
    assert len(first["HUB_HOT_A"]) >= 32
    assert manager.secrets(cfg) == first
    assert manager.base_env().keys().isdisjoint(first)


@pytest.mark.parametrize(
    "change",
    ["shared_token", "shared_port", "external_root", "hub_port", "http", "state"],
)
def test_native_settings_reject_unsafe_runtime_changes(manager, change):
    cfg = set_users(manager)
    if change == "shared_token":
        cfg["users"]["synthetic-b"]["engine_token_env"] = "HUB_HOT_A"
    elif change == "shared_port":
        cfg["users"]["synthetic-b"]["engine_url"] = cfg["users"]["synthetic-a"][
            "engine_url"
        ]
    elif change == "external_root":
        cfg["users"]["synthetic-a"]["download_root"] = str(
            manager.var.parent / "other-app"
        )
    elif change == "hub_port":
        cfg["users"]["synthetic-a"]["engine_url"] = "http://127.0.0.1:8790"
    elif change == "http":
        cfg["public_origin"] = "http://music.test"
        cfg["secure_cookie"] = False
    else:
        cfg["data_dir"] = str(manager.var.parent / "old-ext")
    native.atomic_json(manager.config / "hub.json", cfg)
    with pytest.raises((ValueError, RuntimeError)):
        manager.settings()


def test_non_root_is_enforced_before_any_directory_changes(manager, monkeypatch):
    monkeypatch.setattr(native.os, "getuid", lambda: 0)
    with pytest.raises(RuntimeError, match="package_user_required"):
        manager.guard()


def test_stop_does_not_signal_a_reused_pid(manager, monkeypatch):
    old = {"pid": 4321, "start": "1", "boot": "test", "uid": 1000}
    native.atomic_json(manager.registry, {"supervisor": old, "children": []})
    monkeypatch.setattr(native, "identity", lambda pid: {**old, "start": "2"})
    monkeypatch.setattr(native.os, "pidfd_open", lambda pid: 99)
    monkeypatch.setattr(native.os, "close", lambda fd: None)
    calls = []
    monkeypatch.setattr(
        native.signal, "pidfd_send_signal", lambda *args: calls.append(args)
    )
    manager.stop()
    assert calls == []
    assert not manager.registry.exists()


def test_signal_checks_identity_after_pin(manager, monkeypatch):
    record = {"pid": 4321, "start": "1", "boot": "test", "uid": os.getuid()}
    sequence = []
    monkeypatch.setattr(
        native.os, "pidfd_open", lambda pid: sequence.append("pin") or 99
    )
    monkeypatch.setattr(
        native, "identity", lambda pid: sequence.append("check") or record
    )
    monkeypatch.setattr(
        native.signal, "pidfd_send_signal", lambda fd, sig: sequence.append("signal")
    )
    monkeypatch.setattr(native.os, "close", lambda fd: sequence.append("close"))
    native.send_signal(record, signal.SIGTERM)
    assert sequence == ["pin", "check", "signal", "close"]


def test_lifecycle_operations_are_serialized(manager):
    with manager.lock():
        with pytest.raises(BlockingIOError):
            with manager.lock():
                pytest.fail("second operation entered")


def test_backup_keeps_db_key_credentials_and_excludes_audio(manager):
    (manager.state / "hub.sqlite3").write_bytes(b"synthetic-db")
    (manager.state / "vault.key").write_bytes(b"synthetic-key")
    hot = manager.state / "engines/test"
    hot.mkdir(parents=True)
    (hot / "credentials.json").write_text('{"synthetic":"credential"}')
    downloads = manager.var / "downloads/a"
    downloads.mkdir(parents=True)
    (downloads / "example.mp3").write_bytes(b"synthetic-excluded-audio")
    snapshot = manager.backup()
    assert manager.validated_snapshot() == snapshot
    assert (snapshot / "state/vault.key").read_bytes() == b"synthetic-key"
    assert (snapshot / "state/hub.sqlite3").read_bytes() == b"synthetic-db"
    assert not list(snapshot.rglob("*.mp3"))
    assert manager.active.resolve() == snapshot / "program"
    assert (downloads / "example.mp3").exists()


def test_backup_failure_does_not_publish_completion_or_change_active(
    manager, monkeypatch
):
    before = manager.active.resolve()
    monkeypatch.setattr(
        native.shutil,
        "copytree",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk")),
    )
    with pytest.raises(OSError):
        manager.backup()
    assert manager.active.resolve() == before
    assert not manager.rollback_point.exists()
    assert not list((manager.var / "backups").rglob("complete.json"))


def test_backup_rejects_external_link_before_copying(manager, tmp_path):
    external = tmp_path / "other-application"
    external.write_text("unrelated")
    (manager.state / "bad-link").symlink_to(external)
    with pytest.raises(RuntimeError, match="external_symlink"):
        manager.backup()
    assert external.read_text() == "unrelated"
    assert not manager.rollback_point.exists()


def test_failed_upgrade_restores_matching_data_and_saved_program(manager, monkeypatch):
    db = manager.state / "hub.sqlite3"
    key = manager.state / "vault.key"
    db.write_bytes(b"old-db")
    key.write_bytes(b"old-key")
    old_config = (manager.config / "hub.json").read_bytes()
    snapshot = manager.backup()
    db.write_bytes(b"new-schema-db")
    key.write_bytes(b"new-key")
    rollback = native.Lifecycle(snapshot / "program")
    starts = []
    monkeypatch.setattr(rollback, "start", lambda: starts.append(rollback.program))
    rollback.rollback()
    assert db.read_bytes() == b"old-db" and key.read_bytes() == b"old-key"
    assert (manager.config / "hub.json").read_bytes() == old_config
    assert starts == [snapshot / "program"]
    assert manager.active.resolve() == snapshot / "program"
    assert list(manager.var.glob("failed-state-*"))
    assert manager.validated_snapshot() == snapshot


def test_tampered_backup_is_never_restored(manager, monkeypatch):
    (manager.state / "vault.key").write_bytes(b"original")
    snapshot = manager.backup()
    (snapshot / "state/vault.key").write_bytes(b"tampered")
    rollback = native.Lifecycle(snapshot / "program")
    with pytest.raises(RuntimeError, match="backup_integrity"):
        rollback.rollback()
    assert (manager.state / "vault.key").read_bytes() == b"original"


def test_uninstall_has_no_delete_step_and_post_callback_needs_no_runtime():
    callback = (FPK / "template/cmd/uninstall_callback").read_text()
    assert "rm " not in callback and "python" not in callback
    assert "prepare-upgrade" in (FPK / "template/cmd/uninstall_init").read_text()


def test_status_is_read_only_when_not_running(manager):
    before = {
        p.name: native.inventory(p)
        for p in (manager.config, manager.state, manager.run)
    }
    assert manager.running() is False
    assert {
        p.name: native.inventory(p)
        for p in (manager.config, manager.state, manager.run)
    } == before


def test_offline_assembly_rejects_changed_input_before_running_any_tool(
    tmp_path, monkeypatch
):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "binary").write_bytes(b"original")
    common.write_json(
        inputs / "inputs.json",
        {"pins": common.PINS, "content": common.inventory(inputs)},
    )
    (inputs / "binary").write_bytes(b"changed")
    monkeypatch.setattr(
        prepare.subprocess, "run", lambda *a, **kw: pytest.fail("tool started")
    )
    with pytest.raises(ValueError, match="hash/path/mode"):
        prepare.assemble(inputs, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", ["/etc/passwd", "../secret", "app/../../secret"])
def test_archive_paths_cannot_escape(name):
    with pytest.raises(ValueError, match="unsafe archive"):
        verify.relative_path(name)


@pytest.mark.parametrize(
    "filename", ["a.mp3", "hub.sqlite3", "secrets.json", "vault.key"]
)
def test_payload_rejects_private_data_and_audio(tmp_path, filename):
    (tmp_path / filename).write_bytes(b"must-not-ship")
    with pytest.raises(ValueError):
        common.no_user_data(tmp_path)


def test_icons_have_exact_dimensions_and_opaque_rgb():
    import struct

    for size in (64, 256):
        data = prepare.icon(size)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", data[16:24]) == (size, size)
        assert data[25] == 2  # RGB; no alpha.


def test_manifest_matches_permissions_and_port():
    text = (FPK / "template/manifest").read_text()
    fields = dict(line.split(" = ", 1) for line in text.splitlines())
    privilege = json.loads((FPK / "template/config/privilege").read_text())
    assert (
        fields["appname"]
        == privilege["username"]
        == privilege["groupname"]
        == common.PINS["app_id"]
    )
    assert fields["version"] == common.PINS["package_version"]
    assert "preview" in fields["version"]
    assert fields["service_port"] == str(native.PORT)
    assert privilege["defaults"]["run-as"] == "package"
    assert json.loads((FPK / "template/config/resource").read_text()) == {}


def test_wheel_metadata_has_no_staging_paths_and_remains_valid(tmp_path):
    site = tmp_path / "site"
    dist = site / "example-1.dist-info"
    dist.mkdir(parents=True)
    (site / "bin").mkdir()
    (site / "bin/entry").write_text("#!/absolute/developer/stage/python\n")
    (site / "example.py").write_text("value = 1\n")
    (dist / "direct_url.json").write_text('{"url":"file:///private/build/wheel.whl"}')
    (dist / "RECORD").write_text(
        "example.py,,\nbin/entry,,\nexample-1.dist-info/direct_url.json,,\n"
    )
    prepare.normalize_installed_metadata(site)
    assert not (site / "bin").exists()
    assert not (dist / "direct_url.json").exists()
    data = (dist / "RECORD").read_text()
    assert (
        "example.py,sha256=" in data
        and "direct_url" not in data
        and "bin/entry" not in data
    )
    before = common.inventory(site)
    prepare.normalize_installed_metadata(site)
    assert common.inventory(site) == before


def test_installed_archive_rejects_duplicate_names():
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        for _ in range(2):
            info = tarfile.TarInfo("config/privilege")
            info.size = 2
            archive.addfile(info, io.BytesIO(b"{}"))
    data.seek(0)
    with tarfile.open(fileobj=data) as archive:
        with pytest.raises(ValueError, match="duplicate"):
            verify.members(archive)


@pytest.mark.parametrize(
    "target,valid", [("../b/item", True), ("../../outside", False)]
)
def test_archive_symlinks_may_only_point_within_payload(target, valid):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        info = tarfile.TarInfo("a/link")
        info.type, info.linkname = tarfile.SYMTYPE, target
        archive.addfile(info)
    data.seek(0)
    with tarfile.open(fileobj=data) as archive:
        if valid:
            assert "a/link" in verify.members(archive)
        else:
            with pytest.raises(ValueError, match="unsafe"):
                verify.members(archive)


def test_shell_dispatch_accepts_fnOS_symlink_directory_aliases(tmp_path):
    target, var = tmp_path / "target", tmp_path / "var"
    python = target / "runtime/python/bin/python3"
    python.parent.mkdir(parents=True)
    (target / "native").mkdir()
    var.mkdir()
    python.write_text('#!/bin/sh\nprintf "saved-runtime-ok"\n')
    python.chmod(0o755)
    (var / "active-program").symlink_to(target)
    target_alias, var_alias = tmp_path / "target-alias", tmp_path / "var-alias"
    target_alias.symlink_to(target)
    var_alias.symlink_to(var)
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "id").write_text('#!/bin/sh\nprintf "1001"\n')
    (stub / "id").chmod(
        0o755
    )  # Test wrapper only; real service.py still rejects UID 0.
    env = {
        **os.environ,
        "PATH": str(stub) + ":/usr/bin:/bin",
        "TRIM_APPDEST": str(target_alias),
        "TRIM_PKGVAR": str(var_alias),
    }
    result = subprocess.run(
        ["sh", str(FPK / "template/cmd/_dispatch"), "start"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "saved-runtime-ok"


def test_restart_port_probe_allows_closed_connection_time_wait(manager, monkeypatch):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            connection, _ = listener.accept()
            with connection:
                connection.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b""
        # Closing listener after the accepted socket leaves the server port in TIME_WAIT.
    with socket.socket() as old_probe:
        with pytest.raises(OSError) as error:
            old_probe.bind(("127.0.0.1", port))
        assert error.value.errno == 98
    monkeypatch.setattr(native, "PORT", port)
    manager.check_ports(
        SimpleNamespace(users={}, lan_http_test=False, secure_cookie=True)
    )


def test_restart_port_probe_still_rejects_an_active_listener(manager, monkeypatch):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        address = listener.getsockname()
        listener.listen(1)
        monkeypatch.setattr(native, "PORT", address[1])
        with pytest.raises(OSError) as error:
            manager.check_ports(
                SimpleNamespace(users={}, lan_http_test=False, secure_cookie=True)
            )
        assert error.value.errno == 98
        with socket.create_connection(address, timeout=2):
            accepted, _ = listener.accept()
            accepted.close()
