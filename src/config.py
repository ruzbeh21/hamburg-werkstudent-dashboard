"""Load the project configuration from ``config.yaml``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


def env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment variable; unset or empty means ``default``."""
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Read the YAML config, apply environment overrides and resolve paths.

    Environment overrides (used by the GitHub Actions workflow):

    * ``JOBSUCHE_API_KEY`` – API client id, e.g. from a GitHub Secret.
    * ``JOBS_DATABASE`` – database path relative to the project root.
    * ``KEEP_DESCRIPTIONS`` – ``false`` drops description texts after skill extraction.

    Empty values are ignored, so an unset optional secret never blanks the config.
    """
    with open(path, encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh)

    cfg["api"]["client_id"] = os.environ.get("JOBSUCHE_API_KEY") or cfg["api"]["client_id"]
    cfg["paths"]["database"] = os.environ.get("JOBS_DATABASE") or cfg["paths"]["database"]
    cfg["database"]["keep_descriptions"] = env_flag(
        "KEEP_DESCRIPTIONS", cfg["database"]["keep_descriptions"])
    cfg["paths"] = {key: PROJECT_ROOT / value for key, value in cfg["paths"].items()}
    return cfg
