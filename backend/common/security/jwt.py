#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

from datetime import timedelta
from uuid import uuid4

from fastapi import Depends, Request
from fastapi.security import HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from jose import ExpiredSignatureError, JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from pydantic_core import from_json
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.model import User
from backend.app.admin.schema.user import CurrentUserIns
from backend.common.dataclasses import AccessToken, NewToken, RefreshToken, TokenPayload
from backend.common.exception.errors import AuthorizationError, TokenError
from backend.core.conf import settings
from backend.database.db import async_db_session
from backend.database.redis import redis_client
from backend.utils.serializers import select_as_dict
from backend.utils.timezone import timezone

# JWT authorizes dependency injection
DependsJwtAuth = Depends(HTTPBearer())

password_hash = PasswordHash((BcryptHasher(),))


def get_hash_password(password: str, salt: bytes | None) -> str:
    """
    Encrypt passwords using the hash algorithm

    :param password:
    :param salt:
    :return:
    """
    return password_hash.hash(password, salt=salt)


def password_verify(plain_password: str, hashed_password: str) -> bool:
    """
    Password verification

    :param plain_password: The password to verify
    :param hashed_password: The hash ciphers to compare
    :return:
    """
    return password_hash.verify(plain_password, hashed_password)


async def create_access_token(user_id: str, multi_login: bool, **kwargs) -> AccessToken:
    """
    Generate encryption token

    :param user_id: The user id of the JWT
    :param multi_login: Multipoint login for user
    :param kwargs: Token extra information
    :return:
    """
    expire = timezone.now() + timedelta(seconds=settings.TOKEN_EXPIRE_SECONDS)
    session_uuid = str(uuid4())
    access_token = jwt.encode(
        {"session_uuid": session_uuid, "exp": expire, "sub": user_id},
        settings.TOKEN_SECRET_KEY,
        settings.TOKEN_ALGORITHM,
    )

    if multi_login is False:
        await redis_client.delete_prefix(f"{settings.TOKEN_REDIS_PREFIX}:{user_id}")

    await redis_client.setex(
        f"{settings.TOKEN_REDIS_PREFIX}:{user_id}:{session_uuid}",
        settings.TOKEN_EXPIRE_SECONDS,
        access_token,
    )

    # Token 附加信息单独存储
    if kwargs:
        await redis_client.setex(
            f"{settings.TOKEN_EXTRA_INFO_REDIS_PREFIX}:{session_uuid}",
            settings.TOKEN_EXPIRE_SECONDS,
            json.dumps(kwargs, ensure_ascii=False),
        )

    return AccessToken(access_token=access_token, access_token_expire_time=expire, session_uuid=session_uuid)


async def create_refresh_token(user_id: str, multi_login: bool) -> RefreshToken:
    """
    Generate encryption refresh token, only used to create a new token

    :param user_id: The user id of the JWT
    :param multi_login: multipoint login for user
    :return:
    """
    expire = timezone.now() + timedelta(seconds=settings.TOKEN_REFRESH_EXPIRE_SECONDS)
    refresh_token = jwt.encode(
        {"exp": expire, "sub": user_id},
        settings.TOKEN_SECRET_KEY,
        settings.TOKEN_ALGORITHM,
    )

    if multi_login is False:
        key_prefix = f"{settings.TOKEN_REFRESH_REDIS_PREFIX}:{user_id}"
        await redis_client.delete_prefix(key_prefix)

    await redis_client.setex(
        f"{settings.TOKEN_REFRESH_REDIS_PREFIX}:{user_id}:{refresh_token}",
        settings.TOKEN_REFRESH_EXPIRE_SECONDS,
        refresh_token,
    )
    return RefreshToken(refresh_token=refresh_token, refresh_token_expire_time=expire)


async def create_new_token(user_id: str, refresh_token: str, multi_login: bool, **kwargs) -> NewToken:
    """
    Generate new token

    :param user_id:
    :param refresh_token:
    :param multi_login:
    :param kwargs: Access token extra information
    :return:
    """
    redis_refresh_token = await redis_client.get(f"{settings.TOKEN_REFRESH_REDIS_PREFIX}:{user_id}:{refresh_token}")
    if not redis_refresh_token or redis_refresh_token != refresh_token:
        raise TokenError(msg="Refresh Token 已过期，请重新登录")
    new_access_token = await create_access_token(user_id, multi_login, **kwargs)
    return NewToken(
        new_access_token=new_access_token.access_token,
        new_access_token_expire_time=new_access_token.access_token_expire_time,
        session_uuid=new_access_token.session_uuid,
    )


def get_token(request: Request) -> str:
    """
    Get token for request header

    :return:
    """
    authorization = request.headers.get("Authorization")
    scheme, token = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != "bearer":
        raise TokenError(msg="Token 无效")
    return token


def jwt_decode(token: str) -> TokenPayload:
    """
    Decode token

    :param token:
    :return:
    """
    try:
        # 解析 Token 指定密钥与算法， 密钥在.env配置文件中
        payload = jwt.decode(token, settings.TOKEN_SECRET_KEY, algorithms=[settings.TOKEN_ALGORITHM])
        session_uuid = payload.get("session_uuid") or "debug"  # Debug模式下，session_uuid为debug
        user_id = payload.get("sub")  # 获取用户ID
        expire_time = payload.get("exp")  # 获取过期时间
        if not user_id:  # 如果用户ID不存在，抛出异常
            raise TokenError(msg="Token 无效")
    except ExpiredSignatureError:  # Token 过期
        raise TokenError(msg="Token 已过期")
    except (JWTError, Exception):  # Token 无效
        raise TokenError(msg="Token 无效")
    return TokenPayload(id=int(user_id), session_uuid=session_uuid, expire_time=expire_time)


async def get_current_user(db: AsyncSession, pk: int) -> User:
    """
    Get the current user through token

    :param db:
    :param pk:
    :return:
    """
    from backend.app.admin.crud.crud_user import user_dao

    user = await user_dao.get_with_relation(db, user_id=pk)
    if not user:
        raise TokenError(msg="Token 无效")
    if not user.status:
        raise AuthorizationError(msg="用户已被锁定，请联系系统管理员")
    if user.dept_id:
        if not user.dept.status:
            raise AuthorizationError(msg="用户所属部门已被锁定，请联系系统管理员")
        if user.dept.del_flag:
            raise AuthorizationError(msg="用户所属部门已被删除，请联系系统管理员")
    if user.roles:
        role_status = [role.status for role in user.roles]
        if all(status == 0 for status in role_status):
            raise AuthorizationError(msg="用户所属角色已被锁定，请联系系统管理员")
    return user


def superuser_verify(request: Request) -> bool:
    """
    Verify the current user permissions through token

    :param request:
    :return:
    """
    superuser = request.user.is_superuser
    if not superuser or not request.user.is_staff:
        raise AuthorizationError
    return superuser


async def jwt_authentication(token: str) -> CurrentUserIns:
    """
    JWT authentication

    :param token:
    :return:
    """
    token_payload = jwt_decode(token)  # 解析 Token
    user_id = token_payload.id  # 获取用户ID
    # 获取 Redis 中的 Token，与请求中的 Token 进行比较
    redis_token = await redis_client.get(f"{settings.TOKEN_REDIS_PREFIX}:{user_id}:{token_payload.session_uuid}")
    if not redis_token or token != redis_token:
        raise TokenError(msg="Token 已过期")
    cache_user = await redis_client.get(f"{settings.JWT_USER_REDIS_PREFIX}:{user_id}")  # 获取缓存中的用户信息
    if not cache_user:  # 如果缓存中没有用户信息，则从数据库中获取
        async with async_db_session() as db:
            current_user = await get_current_user(db, user_id)  # 从数据库中获取用户信息
            user = CurrentUserIns(**select_as_dict(current_user))
            await redis_client.setex(
                f"{settings.JWT_USER_REDIS_PREFIX}:{user_id}",
                settings.JWT_USER_REDIS_EXPIRE_SECONDS,
                user.model_dump_json(),
            )  # 将用户信息存入缓存
    else:
        # TODO: 在恰当的时机，应替换为使用 model_validate_json
        # https://docs.pydantic.dev/latest/concepts/json/#partial-json-parsing
        user = CurrentUserIns.model_validate(from_json(cache_user, allow_partial=True))
    return user
