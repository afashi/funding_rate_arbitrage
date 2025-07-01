import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging(log_level=logging.INFO, log_file="funding_rate_arbitrage.log"):
    """
    配置日志记录器，支持输出到控制台和文件。

    功能:
    - 创建一个名为 'arbitrage_bot' 的根日志记录器。
    - 设置日志级别，默认为 INFO。
    - 添加一个将日志输出到控制台的处理器 (StreamHandler)。
    - 添加一个将日志输出到文件的处理器 (RotatingFileHandler)，支持日志轮转，
      防止日志文件无限增大。
    - 为不同的处理器设置不同的日志格式，以便在控制台和文件中清晰地展示信息。

    Args:
        log_level (int, optional): 要设置的日志记录级别。默认为 logging.INFO。
        log_file (str, optional): 日志文件的路径。默认为 "funding_rate_arbitrage.log"。

    Returns:
        logging.Logger: 配置好的日志记录器实例。
    """
    # 获取名为 'arbitrage_bot' 的 logger
    # 如果使用 __name__，则 logger 的名称会是 'logger_config'
    logger = logging.getLogger("arbitrage_bot")
    logger.setLevel(log_level)

    # 防止重复添加 handler
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. 控制台处理器 (Console Handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    # 控制台日志格式更简洁
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)

    # 2. 文件处理器 (File Handler)
    # 使用 RotatingFileHandler 实现日志文件轮转
    # maxBytes=10MB, backupCount=5 表示日志文件最大为10MB，超过则新建一个，最多保留5个备份
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    # 文件日志格式更详细，包含进程ID和线程ID，便于调试
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(process)d - %(threadName)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)

    # 将处理器添加到 logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger