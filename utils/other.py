#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: other.py
Author: YJ
Email: yj1516268@outlook.com
Created Time: 2025-04-25 15:41:04

Description: 一些暂未分类的功能
"""

import random
import string


def turntable(length=16):
    """生成一个指定长度的随机字符串

    :length: 字符串长度，默认为 16
    """
    # 定义字符集：大小写字母 + 数字
    characters = string.ascii_letters + string.digits

    # 随机选择字符
    prize = ''.join(random.choices(characters, k=length))
    return prize


def dice(min=0, max=100):
    """生成一个指定范围内的随机整数

    :min: 最小值，默认为 0
    :max: 最大值，默认为 100
    """
    roll = random.randint(min, max)
    return roll


if __name__ == '__main__':
    print("随机字符串:", turntable())
    print("随机整数:", dice(1, 100))
