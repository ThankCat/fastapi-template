#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局业务异常类

业务代码执行异常时，可以使用 raise xxxError 触发内部错误，它尽可能实现带有后台任务的异常，但它不适用于**自定义响应状态码**
如果要求使用**自定义响应状态码**，则可以通过 return response_base.fail(res=CustomResponseCode.xxx) 直接返回
"""  # noqa: E501

from typing import Any

from fastapi import HTTPException
from starlette.background import BackgroundTask

from backend.common.log import log
from backend.common.response.response_code import CustomErrorCode, StandardResponseCode


class BaseExceptionMixin(Exception):
    """自定义异常基类

    所有自定义异常类的基类，提供了统一的异常处理接口。
    继承自Python内置的Exception类，并添加了额外的功能支持，如错误码、
    错误消息、数据载荷以及后台任务等。

    Args:
        Exception: Python标准异常基类

    Attributes:
        code (int): 错误码
        msg (str): 错误消息
        data (Any): 附加数据
        background (BackgroundTask | None): 后台任务对象
    """

    code: int

    def __init__(self, *, msg: str = None, data: Any = None, background: BackgroundTask | None = None):
        self.msg = msg
        self.data = data
        # The original background task: https://www.starlette.io/background/
        self.background = background


class HTTPError(HTTPException):
    """HTTP异常类

    继承自FastAPI的HTTPException，用于处理HTTP相关的异常情况。
    提供了对HTTP状态码、错误消息和响应头的支持。

    Args:
        HTTPException: FastAPI的HTTP异常基类

    Attributes:
        code (int): HTTP状态码
        msg (Any): 错误消息
        headers (dict[str, Any] | None): HTTP响应头
    """

    def __init__(self, *, code: int, msg: Any = None, headers: dict[str, Any] | None = None):
        super().__init__(status_code=code, detail=msg, headers=headers)


class CustomError(BaseExceptionMixin):
    """自定义错误类

    用于处理自定义业务错误的异常类。继承自BaseExceptionMixin基类，
    通过CustomErrorCode枚举类来定义具体的错误类型。

    Args:
        error (CustomErrorCode): 自定义错误码枚举对象
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): 从CustomErrorCode获取的错误码
    """

    def __init__(self, *, error: CustomErrorCode, data: Any = None, background: BackgroundTask | None = None):
        self.code = error.code
        super().__init__(msg=error.msg, data=data, background=background)


class RequestError(BaseExceptionMixin):
    """请求错误异常类

    用于处理HTTP 400 Bad Request类型的错误。继承自BaseExceptionMixin基类，
    用于表示客户端请求存在语法错误或无法被服务器理解的情况。

    Args:
        msg (str, optional): 错误消息. 默认为"Bad Request"
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): HTTP 400状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_400

    def __init__(self, *, msg: str = "Bad Request", data: Any = None, background: BackgroundTask | None = None):
        super().__init__(msg=msg, data=data, background=background)


class ForbiddenError(BaseExceptionMixin):
    """禁止访问错误异常类

    用于处理HTTP 403 Forbidden类型的错误。继承自BaseExceptionMixin基类，
    表示服务器理解请求但拒绝授权的情况。

    Args:
        msg (str, optional): 错误消息. 默认为"Forbidden"
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): HTTP 403状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_403

    def __init__(self, *, msg: str = "Forbidden", data: Any = None, background: BackgroundTask | None = None):
        super().__init__(msg=msg, data=data, background=background)


class NotFoundError(BaseExceptionMixin):
    """资源未找到错误异常类

    用于处理HTTP 404 Not Found类型的错误。继承自BaseExceptionMixin基类，
    表示服务器无法找到请求的资源的情况。

    Args:
        msg (str, optional): 错误消息. 默认为"Not Found"
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): HTTP 404状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_404

    def __init__(self, *, msg: str = "Not Found", data: Any = None, background: BackgroundTask | None = None):
        super().__init__(msg=msg, data=data, background=background)


class ServerError(BaseExceptionMixin):
    """服务器内部错误异常类

    用于处理HTTP 500 Internal Server Error类型的错误。继承自BaseExceptionMixin基类，
    表示服务器遇到意外情况，无法完成请求的情况。

    Args:
        msg (str, optional): 错误消息. 默认为"Internal Server Error"
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): HTTP 500状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_500

    def __init__(
        self, *, msg: str = "Internal Server Error", data: Any = None, background: BackgroundTask | None = None
    ):
        super().__init__(msg=msg, data=data, background=background)


class GatewayError(BaseExceptionMixin):
    """网关错误异常类

    用于处理HTTP 502 Bad Gateway类型的错误。继承自BaseExceptionMixin基类，
    表示作为网关或代理工作的服务器尝试执行请求时，从上游服务器接收到无效的响应。

    Args:
        msg (str, optional): 错误消息. 默认为"Bad Gateway"
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): HTTP 502状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_502

    def __init__(self, *, msg: str = "Bad Gateway", data: Any = None, background: BackgroundTask | None = None):
        super().__init__(msg=msg, data=data, background=background)


class AuthorizationError(BaseExceptionMixin):
    """授权错误异常类

    用于处理HTTP 401 Unauthorized类型的错误。继承自BaseExceptionMixin基类，
    表示请求未通过身份验证或权限验证的情况。

    Args:
        msg (str, optional): 错误消息. 默认为"Permission Denied"
        data (Any, optional): 附加的错误数据. 默认为None
        background (BackgroundTask | None, optional): 后台任务对象. 默认为None

    Attributes:
        code (int): HTTP 401状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_401

    def __init__(self, *, msg: str = "Permission Denied", data: Any = None, background: BackgroundTask | None = None):
        super().__init__(msg=msg, data=data, background=background)


class TokenError(HTTPError):
    """令牌错误异常类

    用于处理Token相关的认证错误。继承自HTTPError基类，
    主要用于处理未通过Token认证或Token无效的情况。

    Args:
        msg (str, optional): 错误消息. 默认为"Not Authenticated"
        headers (dict[str, Any] | None, optional): HTTP响应头. 默认为None

    Attributes:
        code (int): HTTP 401状态码，从StandardResponseCode获取
    """

    code = StandardResponseCode.HTTP_401

    def __init__(self, *, msg: str = "Not Authenticated", headers: dict[str, Any] | None = None):
        super().__init__(code=self.code, msg=msg, headers=headers or {"WWW-Authenticate": "Bearer"})


class MustError(BaseExceptionMixin):
    code = StandardResponseCode.HTTP_8520

    def __init__(self, *, msg: str = "说你错了，你就错了", data: Any = None, background: BackgroundTask | None = None):
        log.error("这是一个强制错误")
        super().__init__(msg=msg, data=data, background=background)
