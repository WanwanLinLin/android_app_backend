import os
import time
import logging
import openai
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from setting import config_data


def LOG(message, level: str = "INFO"):
    if level == config_data["LOG_CONFIG"]["log_level"]:
        if level == "INFO":
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            logging.info(message)
        else:
            logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
            logger1 = logging.getLogger("python_multipart")     # 直接禁掉某些模块的日志
            logger1.setLevel(logging.WARNING)
            logger2 = logging.getLogger("httpx")     # 直接禁掉某些模块的日志
            logger2.setLevel(logging.WARNING)
            logger3 = logging.getLogger("websockets")     # 直接禁掉某些模块的日志
            logger3.setLevel(logging.WARNING)
            logging.debug(message)
