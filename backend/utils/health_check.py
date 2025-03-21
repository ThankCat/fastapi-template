#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from math import ceil

from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

from backend.common.exception import errors


def ensure_unique_route_names(app: FastAPI) -> None:
    """
    检查路由名称是否唯一

    :param app:
    :return:
    """
    temp_routes = set()  # 创建一个空的集合，用于存储路由名称
    for route in app.routes:  # 遍历所有路由
        if isinstance(route, APIRoute):  # 如果是 APIRoute 类型
            if route.name in temp_routes:  # 如果路由名称已经存在于集合中
                raise ValueError(f"Non-unique route name: {route.name}")
            temp_routes.add(route.name)


async def http_limit_callback(request: Request, response: Response, expire: int):
    """
    请求限制时的默认回调函数

    :param request:
    :param response:
    :param expire: 剩余毫秒
    :return:
    """
    expires = ceil(expire / 1000)
    raise errors.HTTPError(code=429, msg="请求过于频繁，请稍后重试", headers={"Retry-After": str(expires)})
