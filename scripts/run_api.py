from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import default_config_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=default_config_path(), help="Path to YAML config file")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.reload:
        os.environ["GRAPH_CONFIG"] = args.config
        uvicorn.run("controller.app:app", host=args.host, port=args.port, reload=True)
        return

    from controller.app import create_app
    app = create_app(args.config)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

