"""Offline, disposable optional-SDK probe. Never imports MusicBox in the supervisor."""

import argparse
import importlib.metadata
import os
import tempfile
from pathlib import Path


def netease():
    if importlib.metadata.version("NetEase-MusicBox") != "0.5.3":
        raise RuntimeError("fixed MusicBox version required")
    with tempfile.TemporaryDirectory(prefix="hub-netease-probe-") as directory:
        for name in ("CONFIG", "CACHE", "DATA", "RUNTIME"):
            path = Path(directory) / name.lower()
            path.mkdir(mode=0o700)
            os.environ[f"XDG_{name}_HOME" if name != "RUNTIME" else "XDG_RUNTIME_DIR"] = str(path)
        # Import the actual native dependencies and exercise both crypto paths offline.
        import qrcode
        import requests_cache
        from NEMbox.api import NetEase
        from NEMbox.encrypt import eapi_encrypt, encrypted_request
        from rapidfuzz import fuzz

        assert callable(NetEase) and callable(requests_cache.CachedSession)
        assert fuzz.ratio("offline", "offline") == 100
        assert fuzz.ratio.__module__ == "rapidfuzz.fuzz_py"
        qr = qrcode.QRCode()
        qr.add_data("offline-probe")
        qr.make(fit=True)
        assert qr.modules
        assert set(encrypted_request({"probe": True})) == {"params", "encSecKey"}
        assert eapi_encrypt("/api/song/detail", {"ids": "[]"})["params"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netease", action="store_true")
    args = parser.parse_args()
    if args.netease:
        netease()
