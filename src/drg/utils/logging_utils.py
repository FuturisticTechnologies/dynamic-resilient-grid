"""Structured logging with optional Azure Application Insights export."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

_CONFIGURED = False
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"


def setup_logging(level: str | int = "INFO", *, app_insights: bool = True) -> None:
    """Configure root logging once per process.

    When ``APPLICATIONINSIGHTS_CONNECTION_STRING`` is present and the
    ``opencensus-ext-azure`` package is installed, logs are additionally
    shipped to Azure Monitor so the deployed Container App is observable.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if app_insights and conn:
        try:  # pragma: no cover - only exercised in Azure
            from opencensus.ext.azure.log_exporter import AzureLogHandler

            handlers.append(AzureLogHandler(connection_string=conn))
        except Exception as exc:  # pragma: no cover
            logging.getLogger(__name__).warning("App Insights handler unavailable: %s", exc)

    logging.basicConfig(level=level, format=_FORMAT, handlers=handlers, force=True)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    setup_logging(os.getenv("DRG_LOG_LEVEL", "INFO"))
    return logging.getLogger(name or "drg")
