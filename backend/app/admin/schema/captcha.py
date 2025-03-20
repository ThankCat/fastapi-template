#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pydantic import Field

from backend.common.schema import SchemaBase


class GetCaptchaDetail(SchemaBase):
    image_type: str = Field(description="图片类型")
    image: str = Field(description="图片内容")
    code: str = Field(description="验证码")  # 开发环境使用
