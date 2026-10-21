import argparse
import os

import uvicorn

from .app import create_app
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description="fnOS Music Hub development server")
    parser.add_argument("--config", default=os.environ.get("HUB_CONFIG", "config.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    settings = Settings.load(args.config)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
