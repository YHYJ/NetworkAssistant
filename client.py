#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: client.py
Author: YJ
Email: yj1516268@outlook.com
Created Time: 2025-10-15 13:39:32

Description: 网络小助手客户端，获取指定网络接口的信息，并发布到 MQTT
"""

from datetime import datetime
import os
import queue
import socket
import time

from logwrapper import get_logger

from transmitter.mqtt import Transmitter
from utils.config import scheduler


def get_ip_address(interface, logger):
    """获取指定网络接口的 IPv4 地址

    :interface: 网络接口名
    logger: 日志记录器
    """
    try:
        import fcntl
        import struct
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip = fcntl.ioctl(s.fileno(), 0x8915,
                         struct.pack('256s',
                                     interface[:15].encode('utf-8')))[20:24]
        return socket.inet_ntoa(ip)
    except (OSError, IOError, ImportError) as e:
        logger.error("无法获取网络接口 '{}' 的信息: {}".format(interface, e))
        return None


def main(config: dict):
    """主函数

    :config: 配置项
    """
    app_conf = config.get('app', {})
    name = app_conf.get('name', 'Network Assistant')
    version = app_conf.get('version', 'v0.0.0')
    client_conf = config.get('client', {})
    name = client_conf.get('name', 'TODO')
    interface = client_conf.get('interface', 'wlan0')
    mqtt_conf = config.get('mqtt', {})
    logger_conf = config.get('logger', {})

    # 初始化日志记录器
    logger = get_logger(logfolder='logs', config=logger_conf)

    # 启动
    logger.info('Start {} Client {}'.format(name, version))

    # 获取指定网络接口的 IP
    ip = get_ip_address(interface, logger)

    if ip is None:
        return

    # 构造消息
    payload = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Name": name,
        "IP": ip,
    }

    transfer = queue.Queue()
    transmitter = Transmitter(mqtt_conf, transfer, logger)
    transmitter.sender(payload)
    time.sleep(0.1)
    transmitter.stop()


if __name__ == "__main__":
    conf = 'conf'
    confile = os.path.join(conf, 'app.toml')

    # 程序配置项
    config = scheduler(confile)

    main(config)
