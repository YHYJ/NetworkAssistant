#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: server.py
Author: YJ
Email: yj1516268@outlook.com
Created Time: 2025-10-17 09:35:52

Description: 网络小助手服务端，从 MQTT 订阅各客户端发布的网络接口信息
"""

import os
import queue

from logwrapper import get_logger

from transmitter.mqtt import Transmitter
from utils.config import scheduler


def main(config: dict):
    """主函数

    :config: 配置项
    """
    app_conf = config.get('app', {})
    name = app_conf.get('name', 'Network Assistant')
    version = app_conf.get('version', 'v0.0.0')
    mqtt_conf = config.get('mqtt', {})
    logger_conf = config.get('logger', {})

    # 初始化日志记录器
    logger = get_logger(logfolder='logs', config=logger_conf)

    # 启动
    logger.info('Start {} Server {}'.format(name, version))

    transfer = queue.Queue()

    # 创建 Transmitter 实例
    transmitter = Transmitter(mqtt_conf, transfer, logger)

    try:
        transmitter.receiver()

        while True:
            try:
                data = transfer.get(timeout=1)
                logger.info(data)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error('处理数据时出错: {}'.format(e))
    except KeyboardInterrupt:
        logger.info("检测到键盘中断，退出程序")
    except Exception as e:
        logger.error("程序发生错误：{}".format(e))
    finally:
        transmitter.stop()
        logger.info("已退出")


if __name__ == "__main__":
    conf = 'conf'
    confile = os.path.join(conf, 'app.toml')

    # 程序配置项
    config = scheduler(confile)

    main(config)
