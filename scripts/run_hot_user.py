"""Start one isolated native Hot runtime for a configured, verified fnOS GUID."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub.config import Settings
from hub.paths import engine_directory

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", default="config.json")
parser.add_argument("--guid", required=True)
parser.add_argument("--binary", required=True)
args = parser.parse_args()
settings = Settings.load(args.config)
os.umask(0o077)
engine = settings.users[args.guid]
token = os.environ.get(engine.engine_token_env, "")
if len(token) < 16:
    parser.error(
        "the configured engine token environment variable needs at least 16 characters"
    )
data = engine_directory(settings, args.guid)
data.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(data.parent, 0o700)
os.chmod(data, 0o700)
file = data / "settings.json"
if not file.exists():
    fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(
            {"autoDowngrade": False, "duplicateStrategy": "rename", "maxConcurrent": 2},
            output,
        )
engine.download_root.mkdir(parents=True, exist_ok=True, mode=0o700)
origin = urlsplit(engine.engine_url)
env = {
    **os.environ,
    "HOTDOWNLOADER_DATA_DIR": str(data),
    "HOTDOWNLOADER_DOWNLOAD_DIR": str(engine.download_root),
    "HOTDOWNLOADER_BIND": f"127.0.0.1:{origin.port or 80}",
    "HOTDOWNLOADER_TOKEN": token,
}
env.pop("AUTH_USERNAME", None)
env.pop("AUTH_PASSWORD", None)
binary = Path(args.binary).resolve(strict=True)
os.execve(binary, [str(binary)], env)
