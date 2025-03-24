#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from asyncio import create_task

from asgiref.sync import sync_to_async
from fastapi import Response
from starlette.datastructures import UploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.app.admin.schema.opera_log import CreateOperaLogParam
from backend.app.admin.service.opera_log_service import opera_log_service
from backend.common.dataclasses import RequestCallNext
from backend.common.enums import OperaLogCipherType, StatusType
from backend.common.log import log
from backend.core.conf import settings
from backend.utils.encrypt import AESCipher, ItsDCipher, Md5Cipher
from backend.utils.timezone import timezone
from backend.utils.trace_id import get_request_trace_id


class OperaLogMiddleware(BaseHTTPMiddleware):
    """操作日志中间件"""

    async def dispatch(self, request: Request, call_next) -> Response:
        # 排除记录白名单
        path = request.url.path  # 获取请求路径
        # 判断是否在排除列表中 or 非 api 路径
        if path in settings.OPERA_LOG_PATH_EXCLUDE or not path.startswith(f"{settings.FASTAPI_API_V1_PATH}"):
            return await call_next(request)

        # 请求解析
        try:
            # 此信息依赖于 jwt 中间件
            username = request.user.username  # 从 JWT 中获取用户名
        except AttributeError:
            username = None
        method = request.method  # 获取请求方法
        args = await self.get_request_args(request)  # 获取请求参数
        args = await self.desensitization(args)  # 脱敏处理

        # 执行请求
        start_time = timezone.now()  # 请求开始时间
        request_next = await self.execute_request(request, call_next)  # 执行请求
        end_time = timezone.now()  # 请求结束时间
        cost_time = round((end_time - start_time).total_seconds() * 1000.0, 3)  # 计算请求耗时

        # 此信息只能在请求后获取
        _route = request.scope.get("route")  # 获取路由对象
        summary = getattr(_route, "summary", None) or ""  # 获取路由摘要

        # 日志创建
        opera_log_in = CreateOperaLogParam(
            trace_id=get_request_trace_id(request),
            username=username,
            method=method,
            title=summary,
            path=path,
            ip=request.state.ip,
            country=request.state.country,
            region=request.state.region,
            city=request.state.city,
            user_agent=request.state.user_agent,
            os=request.state.os,
            browser=request.state.browser,
            device=request.state.device,
            args=args,
            status=request_next.status,
            code=request_next.code,
            msg=request_next.msg,
            cost_time=cost_time,
            opera_time=start_time,
        )
        create_task(opera_log_service.create(obj_in=opera_log_in))  # 创建异步任务来保存操作日志到数据库

        # 错误抛出
        err = request_next.err
        if err:
            raise err from None

        return request_next.response

    async def execute_request(self, request: Request, call_next) -> RequestCallNext:
        """执行请求"""
        code = 200  # 默认状态码
        msg = "Success"  # 默认消息
        status = StatusType.enable  # 默认状态为启用
        err = None  # 错误对象初始化为空
        response = None  # 响应对象初始化为空
        try:
            response = await call_next(request)  # 将request传递给下一个中间件或路由处理程序
            code, msg = self.request_exception_handler(
                request, code, msg
            )  # 进入异常处理检查是否有异常状态并更新状态码和消息
        except Exception as e:
            log.error(f"请求异常: {e}")
            # code 处理包含 SQLAlchemy 和 Pydantic
            code = getattr(e, "code", None) or code
            msg = getattr(e, "msg", None) or msg
            status = StatusType.disable
            err = e

        return RequestCallNext(code=str(code), msg=msg, status=status, err=err, response=response)

    @staticmethod
    def request_exception_handler(request: Request, code: int, msg: str) -> tuple[str, str]:
        """请求异常处理器"""
        exception_states = [
            "__request_http_exception__",
            "__request_validation_exception__",
            "__request_pydantic_user_error__",
            "__request_assertion_error__",
            "__request_custom_exception__",
            "__request_all_unknown_exception__",
            "__request_cors_500_exception__",
        ]  # 异常状态列表
        for state in exception_states:
            exception = getattr(request.state, state, None)  # 获取异常状态
            if exception:  # 如果存在异常状态
                code = exception.get("code")  # 更新状态码
                msg = exception.get("msg")  # 更新消息
                log.error(f"请求异常: {msg}")  # 记录错误日志
                break
        return code, msg

    @staticmethod
    async def get_request_args(request: Request) -> dict:
        """获取请求参数"""
        args = dict(request.query_params)  # 获取查询参数
        args.update(request.path_params)  # 路径参数更新到参数字典
        # Tip: .body() 必须在 .form() 之前获取
        # https://github.com/encode/starlette/discussions/1933
        body_data = await request.body()  # 获取请求体数据
        form_data = await request.form()  # 获取表单数据
        if len(form_data) > 0:
            """
            - isinstance(v, UploadFile) : 判断值是否是上传的文件
            - 如果是文件： v.filename 获取文件名
            - 如果不是文件：直接使用值 v
            """
            args.update({k: v.filename if isinstance(v, UploadFile) else v for k, v in form_data.items()})
        else:
            if body_data:
                # 获取请求体数据的 Content-Type 并去除分号后的部分
                content_type = request.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if content_type == "application/json":
                    json_data = await request.json()  # JSON 数据
                    if isinstance(json_data, bytes):  # 过度防御
                        json_data = json_data.decode("utf-8")
                    if isinstance(json_data, dict):  # 字典数据
                        args.update(json_data)  # 字典数据更新到参数字典
                    else:
                        # 注意：非字典数据默认使用 body 作为键
                        args.update({"body": json_data})
                else:
                    args.update({"body": str(body_data)})
        return args

    @staticmethod
    @sync_to_async
    def desensitization(args: dict) -> dict | None:
        """
        脱敏处理

        :param args:
        :return:
        """
        if not args:  # 空字典处理
            args = None
        else:
            match settings.OPERA_LOG_ENCRYPT_TYPE:
                case OperaLogCipherType.aes:  # AES加密 ：高级加密标准，可逆加密
                    for key in args.keys():
                        if key in settings.OPERA_LOG_ENCRYPT_KEY_INCLUDE:
                            args[key] = (AESCipher(settings.OPERA_LOG_ENCRYPT_SECRET_KEY).encrypt(args[key])).hex()
                case OperaLogCipherType.md5:  # MD5加密 ：消息摘要算法，不可逆加密
                    for key in args.keys():
                        if key in settings.OPERA_LOG_ENCRYPT_KEY_INCLUDE:
                            args[key] = Md5Cipher.encrypt(args[key])
                case OperaLogCipherType.itsdangerous:  # itsdangerous加密 ：Flask作者开发的加密库，常用于token生成
                    for key in args.keys():
                        if key in settings.OPERA_LOG_ENCRYPT_KEY_INCLUDE:
                            args[key] = ItsDCipher(settings.OPERA_LOG_ENCRYPT_SECRET_KEY).encrypt(args[key])
                case OperaLogCipherType.plan:  # 明文 ：不进行加密
                    pass
                case _:  # 默认处理 ：用星号替换
                    for key in args.keys():
                        if key in settings.OPERA_LOG_ENCRYPT_KEY_INCLUDE:
                            args[key] = "******"
        return args
