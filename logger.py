import logging
import os
from datetime import datetime

LOG_DIR = "logs"

def get_logger(name: str = "trading_bot", level: int = logging.DEBUG) -> logging.Logger:
    """
    Returns a logger that writes to both console and a daily log file.

    logs/
      trading_bot_2026-03-28.log
      trading_bot_2026-03-29.log
      ...

    Usage:
        from utils.logger import get_logger
        log = get_logger()
        log.info("Bot started")
        log.warning("Unusual condition")
        log.error("Something failed")
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ── Console handler ───────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)       # INFO and above in terminal
    console_handler.setFormatter(formatter)

    # ── File handler (daily rotating file) ───────────────────────────
    today     = datetime.now().strftime("%Y-%m-%d")
    log_file  = os.path.join(LOG_DIR, f"{name}_{today}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)         # everything goes to file
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger