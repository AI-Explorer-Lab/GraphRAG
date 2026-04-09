from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from lineage_graphrag.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    default_config = "configs/local.yaml" if Path("configs/local.yaml").exists() else "configs/base.yaml"
    parser.add_argument("--config", default=default_config, help="Path to YAML config file")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    app = create_app(args.config)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
