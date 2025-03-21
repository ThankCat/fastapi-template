#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socketio

from socketio.async_server import AsyncServer

from backend.app.task.conf import task_settings
from backend.common.log import log
from backend.common.security.jwt import jwt_authentication
from backend.core.conf import settings
from backend.database.redis import redis_client

# 参考：https://python-socketio.readthedocs.io/en/stable/api.html#socketio.AsyncServer
sio: AsyncServer = socketio.AsyncServer(
    # 此配置是为了集成 celery 实现消息订阅，如果你不使用 celery，可以直接删除此配置，不会造成任何影响
    client_manager=socketio.AsyncRedisManager(
        f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:"
        f"{settings.REDIS_PORT}/{task_settings.CELERY_BROKER_REDIS_DATABASE}"
    )
    if task_settings.CELERY_BROKER == "redis"
    else socketio.AsyncAioPikaManager(
        (
            f"amqp://{task_settings.RABBITMQ_USERNAME}:{task_settings.RABBITMQ_PASSWORD}@"
            f"{task_settings.RABBITMQ_HOST}:{task_settings.RABBITMQ_PORT}"
        )
    ),  # 根据设置的消息队列类型，选择不同的客户端管理器
    async_mode="asgi",  # 异步模式
    cors_allowed_origins=settings.CORS_ALLOWED_ORIGINS,  # 允许跨域的域名
    cors_credentials=True,  # 允许跨域请求携带凭证
    namespaces=["/ws"],  # 指定 Socket.IO 的命名空间列表。
)


@sio.event
async def connect(sid: str, environ: dict, auth: dict) -> bool:
    """
    当客户端连接时触发

    :param sid: 客户端会话 ID，唯一标识每个连接
    :param environ: 请求的环境信息，包括 HTTP 请求头和其他元数据
    :param auth: 授权信息字典，包含 session_uuid 和 token 用于验证连接合法性
    :return: 布尔值，表示连接是否成功
    """
    if not auth:  # 如果没有授权信息
        log.error("ws 连接失败：无授权")
        return False

    session_uuid = auth.get("session_uuid")  # 获取 session_uuid
    token = auth.get("token")  # 获取token
    if not token or not session_uuid:
        log.error("ws 连接失败：授权失败，请检查")
        return False

    # 免授权直连
    if token == settings.WS_NO_AUTH_MARKER:  # 如果token是"internal""
        await redis_client.sadd(settings.TOKEN_ONLINE_REDIS_PREFIX, session_uuid)  # 将session_uuid添加到redis中
        return True

    try:
        await jwt_authentication(token)  # 验证token
    except Exception as e:
        log.info(f"ws 连接失败：{e}")
        return False

    await redis_client.sadd(settings.TOKEN_ONLINE_REDIS_PREFIX, session_uuid)
    return True


@sio.event
async def disconnect(sid):
    """当客户端断开连接时触发"""
    await redis_client.spop(settings.TOKEN_ONLINE_REDIS_PREFIX)
