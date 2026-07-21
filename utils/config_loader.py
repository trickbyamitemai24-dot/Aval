"""Config loader — loads config.yaml with env var substitution."""

import os
import re
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load config.yaml, substituting ${ENV_VAR} with environment values."""
    path = Path(config_path)
    if not path.exists():
        logger.error("Config file not found: %s", path)
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Substitute ${ENV_VAR} with env values
    def replace_env(match):
        var = match.group(1)
        return os.environ.get(var, match.group(0))

    raw = re.sub(r"\$\{(\w+)\}", replace_env, raw)

    config = yaml.safe_load(raw)
    logger.info("Config loaded from %s", path)
    return config or {}