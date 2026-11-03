"""Run the whole pipeline: collect → clean → skills → SQLite → export.

Usage:
    python run.py                 # full run including API collection
    python run.py --skip-collect  # rebuild DB and exports from cached raw data
"""

from __future__ import annotations

import argparse
import logging

from src import analyse, collect, db
from src.config import load_config


def main() -> None:
    """Parse arguments and run the pipeline steps in order."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-collect", action="store_true",
                        help="do not call the API; reuse data/raw")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if not args.skip_collect:
        collect.run()
    db_path = db.build(cfg)
    analyse.export(db_path, cfg["paths"]["export_dir"])


if __name__ == "__main__":
    main()
