"""
Module Logging tập trung cho hệ thống AI Agent Platform.
Tham chiếu: docs/AI_Plan.pdf (Mục 3.1 - Thành viên 5).
"""
import os
import sys
import logging
from typing import Optional


def setup_logger(name: str = "fme", level: Optional[str] = None) -> logging.Logger:
    """Tạo hoặc lấy một Logger có định dạng thống nhất toàn hệ thống.

    Args:
        name: Tên logger (vd: 'fme.chat', 'fme.mcp', 'fme.agent').
        level: Level log (DEBUG, INFO, WARNING, ERROR). Mặc định lấy từ biến LOG_LEVEL hoặc INFO.

    Returns:
        logging.Logger: Đối tượng logger đã cấu hình stream handler.
    """
    logger = logging.getLogger(name)

    log_level_str = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Default logger instance
logger = setup_logger("fme")

__all__ = ["setup_logger", "logger"]
