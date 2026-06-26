from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    parser = argparse.ArgumentParser()
    default_config = "configs/local.yaml" if Path("configs/local.yaml").exists() else "configs/base.yaml"
    parser.add_argument("--config", default=default_config, help="Path to YAML config file")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.reload:
        os.environ["LINEAGE_CONFIG"] = args.config
        uvicorn.run("lineage_graphrag.api.app:app", host=args.host, port=args.port, reload=True)
        return

    from lineage_graphrag.api.app import create_app
    app = create_app(args.config)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
