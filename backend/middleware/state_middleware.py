#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.utils.request_parse import parse_ip_info, parse_user_agent_info


class StateMiddleware(BaseHTTPMiddleware):
    """请求 state 中间件"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        ip_info = await parse_ip_info(request)  # 解析IP信息
        ua_info = parse_user_agent_info(request)  # 解析用户请求头信息

        # 设置附加请求信息
        request.state.ip = ip_info.ip
        request.state.country = ip_info.country
        request.state.region = ip_info.region
        request.state.city = ip_info.city
        request.state.user_agent = ua_info.user_agent
        request.state.os = ua_info.os
        request.state.browser = ua_info.browser
        request.state.device = ua_info.device

        response = await call_next(request)  # 执行后续的中间件和路由处理函数

        return response
