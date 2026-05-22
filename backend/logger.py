"""
服务器管家 - 日志模块
统一提供文件日志和控制台日志
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from .paths import data_dir


def _get_log_file() -> str:
    log_dir = os.path.join(data_dir(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, 'python.log')


def get_logger(name: str = 'server_manager') -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s')

    file_handler = RotatingFileHandler(
        _get_log_file(),
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger
