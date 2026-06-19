"""Lightweight rotating file logging.

So issues found during real-use testing are diagnosable: errors in the sampling
loop and every persisted session are recorded. Lives next to the database at
~/Library/Application Support/WorktimeTracker/worktime.log.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from . import config

_configured = False


def get_logger(name="worktime"):
    global _configured
    if not _configured:
        log_dir = os.path.dirname(config.DB_PATH)
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(log_dir, "worktime.log"), maxBytes=512_000, backupCount=2)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger("worktime")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        _configured = True
    return logging.getLogger(f"worktime.{name}")
