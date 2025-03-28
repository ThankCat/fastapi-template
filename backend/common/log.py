#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import inspect
import logging
import os
import sys

from asgi_correlation_id import correlation_id
from loguru import logger

from backend.core import path_conf
from backend.core.conf import settings


class InterceptHandler(logging.Handler):
    """
    将标准logging日志记录器的日志消息重定向到loguru日志记录器。
    Default handler from examples in loguru documentation.
    See https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord):
        """
        emit 方法是 logging.Handler 类的一个抽象方法，
        必须在子类中实现。它接收一个 logging.LogRecord 对象作为参数，
        该对象包含了日志记录的详细信息。
        """
        # Get corresponding Loguru level if it exists
        try:
            # 尝试从 loguru 日志记录器中获取与 logging 记录级别名称对应的 Loguru 级别名称。
            level = logger.level(record.levelname).name
        except ValueError:
            # 如果在 loguru 日志记录器中找不到对应的级别名称，则使用 logging 记录级别名称。
            level = record.levelno

        # Find caller from where originated the logged message.
        frame = inspect.currentframe()  # 获取当前帧对象（当前正在执行的代码所在的调用栈帧对象）
        depth = 0  # 记录当前调用栈的深度

        """
        这个 while 循环会持续执行，直到满足以下两个条件之一：
        1. frame 变为 None ，这意味着已经回溯到调用栈的顶部，没有更多的调用帧可供回溯。
        2. 既不是初始调用帧（ depth != 0 ），并且当前调用帧的代码文件不是 logging 模块的文件。
        3. frame.f_code.co_filename 是当前调用帧的代码文件的完整路径。
        4. logging.__file__ 是 logging 模块的文件路径。
        """
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back  # 回溯到上一个调用帧
            # print(frame.f_code.co_filename)
            depth += 1  # 深度+1

        # 当跳出循环时，说明 frame.f_code.co_filename != logging.__file__
        # 即找到了实际调用日志记录的代码所在的栈帧

        """`logger.opt` 是 loguru 日志记录器的一个方法
        depth 参数用于指定日志记录时调用栈的深度。
        exception 参数用于指定日志记录时要包含的异常信息。
        log() 是 loguru 库中 logger 对象的一个方法，用于实际记录日志。
        level 是日志的级别
        record.getMessage() 是 logging.LogRecord 对象的一个方法，它返回格式化后的日志消息。
        """
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging():
    """
    设置和配置日志系统
    From https://github.com/benoitc/gunicorn/issues/1572#issuecomment-638391953
    https://github.com/pawamoy/pawamoy.github.io/issues/17
    """
    # Set the logging handler and level
    logging.root.handlers = [InterceptHandler()]  # 设置日志拦截器
    logging.root.setLevel(settings.LOG_STD_LEVEL)  # 设置日志级别

    # Remove all log handlers and propagate to root logger
    for name in logging.root.manager.loggerDict.keys():  # 获取所有已注册的日志器名称
        logging.getLogger(name).handlers = []  # 移除所有已注册的日志器的处理程序

        """
        propagate 属性控制日志消息是否向上传播到父日志器：
        - 当 propagate = True 时，日志消息会传递给父日志器
        - 当 propagate = False 时，日志消息在当前日志器处理后就停止传播
        """
        if "uvicorn.access" in name or "watchfiles.main" in name:
            logging.getLogger(name).propagate = False
        else:
            logging.getLogger(name).propagate = True

        # Debug log handlers
        # logging.debug(f'{logging.getLogger(name)}, {logging.getLogger(name).propagate}')

    # Define the correlation_id default filter function
    # https://github.com/snok/asgi-correlation-id/issues/7
    def correlation_id_filter(record: dict) -> dict:
        """
        为日志记录添加关联 ID（correlation ID），并对关联 ID 进行长度截断处理，然后返回处理后的日志记录。
        """
        # 从 asgi_correlation_id 模块中获取当前的关联 ID，并将其存储在变量 cid
        # # 中。如果当前没有关联 ID，则使用默认值 settings.LOG_CID_DEFAULT_VALUE。
        cid = correlation_id.get(settings.LOG_CID_DEFAULT_VALUE)

        # 将获取到的关联 ID 截取前 settings.LOG_CID_UUID_LENGTH 个字符，
        # 并将其添加到日志记录的字典中，键名为 "correlation_id"。
        record["correlation_id"] = cid[: settings.LOG_CID_UUID_LENGTH]
        # 返回处理后的日志记录，以便后续的日志处理流程继续使用。
        return record

    # Remove default loguru logger
    """
    在 loguru 库中， logger.remove() 方法用于移除之前添加的所有日志处理器。
    在当前代码的 setup_logging 函数里，这行代码的作用是移除默认的 loguru 日志记录器配置，
    后续可通过 logger.configure 重新设置日志处理器。
    """
    logger.remove()

    # Set the loguru default handlers
    # 重新配置 loguru 日志记录器的默认处理器。
    logger.configure(
        handlers=[
            {
                # 将日志输出到标准输出（通常是终端）
                "sink": sys.stdout,
                # 设置日志记录的级别，只有等于或高于该级别的日志才会被记录
                "level": settings.LOG_STD_LEVEL,
                # 应用关联 ID 过滤器，为日志记录添加关联 ID
                "filter": lambda record: correlation_id_filter(record),
                # 设置日志记录的格式，从配置文件中获取日志格式
                "format": settings.LOG_STD_FORMAT,
            }
        ]
    )


def set_custom_logfile():
    """
    设置自定义日志文件
    """
    log_path = path_conf.LOG_DIR  # 获取日志目录路径
    if not os.path.exists(log_path):  # 如果不存在就创建
        os.mkdir(log_path)

    # log files
    log_access_file = os.path.join(log_path, settings.LOG_ACCESS_FILENAME)  # 获取访问日志文件路径
    log_error_file = os.path.join(log_path, settings.LOG_ERROR_FILENAME)  # 获取错误日志文件路径

    # set loguru logger default config
    # https://loguru.readthedocs.io/en/stable/api/logger.html#loguru._logger.Logger.add
    # 设置 loguru 日志记录器的通用配置
    log_config = {
        "format": settings.LOG_FILE_FORMAT,  # 日志格式化模板，从配置文件中获取
        "enqueue": True,  # 启用异步写入，避免日志写入阻塞主程序
        "rotation": "5 MB",  # 当日志文件达到5MB时进行轮转（创建新文件）
        "retention": "7 days",  # 保留最近7天的日志文件，更早的会被删除
        "compression": "tar.gz",  # 对旧的日志文件进行压缩，使用tar.gz格式
    }

    # TRACE = 5
    # DEBUG = 10
    # INFO = 20
    # SUCCESS = 25
    # WARNING = 30
    # ERROR = 40
    # CRITICAL = 50

    # stdout file
    logger.add(
        sink=str(log_access_file),  # 通过日志输出的目标文件路径
        level=settings.LOG_ACCESS_FILE_LEVEL,  # 日志级别，从配置文件获取
        filter=lambda record: record["level"].no <= 25,  # 过滤器：只记录级别小于等于25的日志
        backtrace=False,  # 不显示异常的回溯跟踪信息
        diagnose=False,  # 不显示诊断信息（变量值等详细信息）
        **log_config,  # 使用之前定义的通用日志配置
    )

    # stderr file
    logger.add(
        str(log_error_file),  # 错误日志输出的目标文件路径
        level=settings.LOG_ERROR_FILE_LEVEL,  # 错误日志的级别，从配置文件获取
        filter=lambda record: record["level"].no >= 30,  # 过滤器：只记录级别大于等于30的日志
        backtrace=True,  # 显示异常的回溯跟踪信息
        diagnose=True,  # 显示诊断信息（变量值等详细信息）
        **log_config,  # 使用之前定义的通用日志配置
    )


log = logger
