#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from fast_captcha import img_captcha
from fastapi import APIRouter, Depends, Request
from fastapi_limiter.depends import RateLimiter
from starlette.concurrency import run_in_threadpool

from backend.app.admin.conf import admin_settings
from backend.app.admin.schema.captcha import GetCaptchaDetail
from backend.common.response.response_schema import ResponseSchemaModel, response_base
from backend.database.redis import redis_client

router = APIRouter()


@router.get(
    "",
    summary="获取登录验证码",
    dependencies=[Depends(RateLimiter(times=5, seconds=10))],
)
async def get_captcha(request: Request) -> ResponseSchemaModel[GetCaptchaDetail]:
    """
    此接口可能存在性能损耗，尽管是异步接口，但是验证码生成是IO密集型任务，使用线程池尽量减少性能损耗
    """
    img_type: str = "base64"  # 默认为base64，可根据实际情况进行调整
    img, code = await run_in_threadpool(
        img_captcha, img_byte=img_type
    )  # 线程池中执行 img_captcha 函数, 生成验证码图片和验证码文本
    ip = request.state.ip  # 获取请求的IP地址
    await redis_client.set(
        f"{admin_settings.CAPTCHA_LOGIN_REDIS_PREFIX}:{ip}",
        code,
        ex=admin_settings.CAPTCHA_LOGIN_EXPIRE_SECONDS,
    )  # 将验证码文本存储到Redis中，设置过期时间为 admin_settings.CAPTCHA_LOGIN_EXPIRE_SECONDS 秒
    data = GetCaptchaDetail(
        image_type=img_type, image=img, code=code
    )  # 创建 GetCaptchaDetail 对象，包含验证码图片和图片类型
    return response_base.success(data=data)
