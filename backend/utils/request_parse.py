#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import httpx

from asgiref.sync import sync_to_async
from fastapi import Request
from ip2loc import XdbSearcher
from user_agents import parse

from backend.common.dataclasses import IpInfo, UserAgentInfo
from backend.common.log import log
from backend.core.conf import settings
from backend.core.path_conf import IP2REGION_XDB
from backend.database.redis import redis_client


def get_request_ip(request: Request) -> str:
    """获取请求的 ip 地址"""
    real = request.headers.get("X-Real-IP")  # nginx 代理
    if real:
        ip = real
    else:
        forwarded = request.headers.get("X-Forwarded-For")  # 再检查 X-Forwarded-For
        if forwarded:
            ip = forwarded.split(",")[0]
        else:
            ip = request.client.host  # 最后检查客户端主机头
    # 忽略 pytest
    if ip == "testclient":
        ip = "127.0.0.1"
    return ip


async def get_location_online(ip: str, user_agent: str) -> dict | None:
    """
    在线获取 ip 地址属地，无法保证可用性，准确率较高

    :param ip:
    :param user_agent:
    :return:
    """
    async with httpx.AsyncClient(timeout=3) as client:
        ip_api_url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        headers = {"User-Agent": user_agent}
        try:
            response = await client.get(ip_api_url, headers=headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            log.error(f"在线获取 ip 地址属地失败，错误信息：{e}")
            return None


@sync_to_async
def get_location_offline(ip: str) -> dict | None:
    """
    离线获取 ip 地址属地，无法保证准确率，100%可用

    :param ip:
    :return:
    """
    try:
        cb = XdbSearcher.loadContentFromFile(dbfile=IP2REGION_XDB)
        searcher = XdbSearcher(contentBuff=cb)
        data = searcher.search(ip)
        searcher.close()
        data = data.split("|")
        return {
            "country": data[0] if data[0] != "0" else None,
            "regionName": data[2] if data[2] != "0" else None,
            "city": data[3] if data[3] != "0" else None,
        }
    except Exception as e:
        log.error(f"离线获取 ip 地址属地失败，错误信息：{e}")
        return None


async def parse_ip_info(request: Request) -> IpInfo:
    """
    解析 ip 地址信息
    """
    country, region, city = None, None, None  # 城市，省，国家
    ip = get_request_ip(request)  # 获取请求IP地址
    location = await redis_client.get(
        f"{settings.IP_LOCATION_REDIS_PREFIX}:{ip}"
    )  # 从 redis 中获取 ip 地址信息，使用缓存
    if location:
        country, region, city = location.split("|")
        return IpInfo(ip=ip, country=country, region=region, city=city)
    if settings.IP_LOCATION_PARSE == "online":  # 在线解析IP地址
        location_info = await get_location_online(ip, request.headers.get("User-Agent"))  # 获取IP地址信息
    elif settings.IP_LOCATION_PARSE == "offline":
        location_info = await get_location_offline(ip)
    else:
        location_info = None
    if location_info:
        country = location_info.get("country")
        region = location_info.get("regionName")
        city = location_info.get("city")
        await redis_client.set(
            f"{settings.IP_LOCATION_REDIS_PREFIX}:{ip}",
            f"{country}|{region}|{city}",
            ex=settings.IP_LOCATION_EXPIRE_SECONDS,
        )
    return IpInfo(ip=ip, country=country, region=region, city=city)


def parse_user_agent_info(request: Request) -> UserAgentInfo:
    """
    解析用户请求头信息
    """
    user_agent = request.headers.get("User-Agent")  # 获取请求投
    _user_agent = parse(user_agent)  # 解析用户请求头信息
    os = _user_agent.get_os()  # 获取系统信息
    browser = _user_agent.get_browser()  # 获取浏览器信息
    device = _user_agent.get_device()  # 获取设备信息
    return UserAgentInfo(user_agent=user_agent, device=device, os=os, browser=browser)
