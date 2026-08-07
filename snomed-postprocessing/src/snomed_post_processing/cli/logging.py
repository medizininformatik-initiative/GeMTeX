"""CLI logging configuration helpers."""

from __future__ import annotations

import logging


def set_log_level(log_level: str):
    log_level_ = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(log_level.lower(), logging.INFO)
    logging.basicConfig(level=log_level_)
