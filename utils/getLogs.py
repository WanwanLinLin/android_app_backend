import os
import time
import logging
import openai
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from setting import config_data, LOGS_PATH

LOGS_MAP = {}
simple_logger = logging.getLogger(__name__)


def setup_logging():
    level_name = config_data["LOG_CONFIG"]["log_level"].upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    for name in ("python_multipart", "httpx", "websockets"):
        logging.getLogger(name).setLevel(logging.WARNING)

setup_logging()


def LOG(message, level="INFO"):
    simple_logger.log(getattr(logging, level.upper(), logging.INFO), message)


# def LOG(message, level: str = "INFO"):
#     if level == config_data["LOG_CONFIG"]["log_level"]:
#         if level == "INFO":
#             logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#             logging.info(message)
#         else:
#             logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
#             logger1 = logging.getLogger("python_multipart")     # 直接禁掉某些模块的日志
#             logger1.setLevel(logging.WARNING)
#             logger2 = logging.getLogger("httpx")     # 直接禁掉某些模块的日志
#             logger2.setLevel(logging.WARNING)
#             logger3 = logging.getLogger("websockets")     # 直接禁掉某些模块的日志
#             logger3.setLevel(logging.WARNING)
#             logging.debug(message)


class LogFilter:
    @staticmethod
    def info_filter(record):
        if record.levelname == 'INFO':
            return True
        return False
    
    @staticmethod
    def debug_filter(record):
        if record.levelname == 'DEBUG' or record.levelname == 'INFO':
            return True
        return False

    @staticmethod
    def error_filter(record):
        if record.levelname == 'ERROR':
            return True
        return False


class TimeLoggerRolloverHandler(TimedRotatingFileHandler):
    def __init__(self, filename, when='h', interval=1, backup_count=365, encoding=None, delay=False, utc=False,
                 atTime=None, log_dir=None, api_name=None):
        super(TimeLoggerRolloverHandler, self).__init__(filename, when, interval, backup_count, encoding, delay, utc)
        self.log_dir = log_dir
        self.api_name = api_name

    def doRollover(self):
        """
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        currentTime = int(time.time())
        dstNow = time.localtime(currentTime)[-1]
        log_type = 'info' if self.level == 20 else 'error'
        dfn = f"{self.log_dir}/{self.api_name}.{datetime.now().strftime('%Y-%m-%d')}.{log_type}.log"
        self.baseFilename = dfn
        if not self.delay:
            self.stream = self._open()
        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt = newRolloverAt + self.interval
        if (self.when == 'MIDNIGHT' or self.when.startswith('W')) and not self.utc:
            dstAtRollover = time.localtime(newRolloverAt)[-1]
            if dstNow != dstAtRollover:
                if not dstNow:
                    addend = -3600
                else:
                    addend = 3600
                newRolloverAt += addend
        self.rolloverAt = newRolloverAt

    @staticmethod
    def get_log(api_name: str, dir_name: str):
        log_info_level = logging.INFO if config_data["LOG_CONFIG"]["log_level"] == "INFO" else logging.DEBUG
        log_dir = os.path.join(LOGS_PATH, dir_name)
        os.makedirs(log_dir, exist_ok=True)
        new_formatter = '[%(levelname)s]%(asctime)s#>[%(pathname)s]:%(lineno)s  %(message)s'
        fmt = logging.Formatter(new_formatter)
        log_error_file = f"{log_dir}/{api_name}.{datetime.now().strftime('%Y-%m-%d')}.error.log"
        log_info_file = f"{log_dir}/{api_name}.{datetime.now().strftime('%Y-%m-%d')}.info.log"

        error_handler = TimeLoggerRolloverHandler(log_error_file, when='MIDNIGHT', log_dir=log_dir, api_name=api_name)
        error_handler.addFilter(LogFilter.error_filter)
        error_handler.setFormatter(fmt)
        error_handler.setLevel(logging.ERROR)

        info_handel = TimeLoggerRolloverHandler(log_info_file, when='MIDNIGHT', log_dir=log_dir, api_name=api_name)
        if config_data["LOG_CONFIG"]["log_level"] == "INFO":
            info_handel.setFormatter(fmt)
            info_handel.addFilter(LogFilter.info_filter)
            info_handel.setLevel(log_info_level)
        elif config_data["LOG_CONFIG"]["log_level"] == "DEBUG":
            info_handel.setFormatter(fmt)
            info_handel.addFilter(LogFilter.debug_filter)
            info_handel.setLevel(log_info_level)
            
        log_info = logging.getLogger(log_info_file)
        log_info.setLevel(log_info_level)
        # log_info.handlers.clear()
        if dir_name + api_name not in LOGS_MAP:
            LOGS_MAP[dir_name + api_name] = 1
            log_info.addHandler(info_handel)
            log_info.addHandler(error_handler)

        return log_info


generic_tts_logger = TimeLoggerRolloverHandler.get_log("generic", "TTS")