import logging
import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

_log_listeners: List[Callable[[str], None]] = []
_recent_logs: deque = deque(maxlen=200)


class FlowLogFormatter(logging.Formatter):
    """Custom formatter providing cleanly formatted [HH:MM:SS] logs."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        prefix = f"[{timestamp}]"
        if record.levelno >= logging.ERROR:
            msg = f"{prefix} [ERROR] {record.getMessage()}"
        elif record.levelno >= logging.WARNING:
            msg = f"{prefix} [WARN] {record.getMessage()}"
        else:
            msg = f"{prefix} {record.getMessage()}"

        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


class BroadcastHandler(logging.Handler):
    """Handler that pushes formatted log messages to in-memory buffers and callbacks."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _recent_logs.append(msg)
            for listener in list(_log_listeners):
                try:
                    listener(msg)
                except Exception:
                    pass
        except Exception:
            self.handleError(record)


def add_log_listener(listener: Callable[[str], None]) -> None:
    """Register a listener callback for new log events (e.g. WebSocket)."""
    if listener not in _log_listeners:
        _log_listeners.append(listener)


def remove_log_listener(listener: Callable[[str], None]) -> None:
    """Remove a previously registered log listener."""
    if listener in _log_listeners:
        _log_listeners.remove(listener)


def get_recent_logs() -> List[str]:
    """Retrieve the recent in-memory log buffer."""
    return list(_recent_logs)


def setup_logger(log_file_path: Optional[str] = "logs/google_flow_auto.log", level: int = logging.INFO) -> logging.Logger:
    """Configure the root Google Flow Auto logger with console and file output."""
    logger = logging.getLogger("google_flow_auto")
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = FlowLogFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_file_path:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # In-memory broadcast handler for UI
    broadcast_handler = BroadcastHandler()
    broadcast_handler.setFormatter(formatter)
    logger.addHandler(broadcast_handler)

    return logger


logger = logging.getLogger("google_flow_auto")
