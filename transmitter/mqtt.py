#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: mqtt.py
Author: YJ
Email: yj1516268@outlook.com
Created Time: 2025-10-17 08:39:21

Description: 数据传输器 —— 和 MQTT 进行数据交互
"""

import json

import paho.mqtt.client as mqtt

from utils.other import turntable


class Transmitter:
    """数据传输器"""

    def __init__(self, config, transfer, logger):
        """初始化

        :config: 数据传输器配置
        :transfer: 数据中转站
        :logger: 日志记录器
        """
        self.transfer = transfer
        self.logger = logger

        # 连接信息
        self.host = config.get('host', '127.0.0.1')
        self.port = config.get('port', 1883)
        self.username = config.get('username', None)
        self.password = config.get('password', None)
        self.client_id = config.get('client_id', None)
        self.qos = config.get('qos', 1)
        self.keepalive = config.get('keepalive', 60)
        self.retain = config.get('retain', False)
        self.tls_ca_certs = config.get('tls_ca_certs', None)

        # Topic
        self.topic = config.get('topic', '/FROM/Gateway/Info')
        self.topic_will = config.get('topic_will', 'status/offline')

        self._connected = False  # 标记连接状态
        # Client ID 未设置时自动生成
        if not self.client_id:
            self.client_id = turntable()
        client_id = self.client_id
        clean_session = config.get('clean_session', True)
        self.client = mqtt.Client(client_id=client_id,
                                  clean_session=clean_session)

        # 设置回调函数
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe

        # 连接 MQTT
        self._connect()

    def _on_connect(self, client, userdata, flags, rc):
        """连接回调函数"""
        if rc == 0 or rc.getName() == "Success":
            self.logger.info("已连接 MQTT，客户端 ID = {}".format(self.client_id))
        else:
            self.logger.error("连接 MQTT 失败，错误码: {}".format(rc))
            self.stop()

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调函数"""
        if rc != 0:  # 非正常断开连接
            self.logger.warning("与 MQTT 服务器连接断开，正在重新连接")
            self._connected = False  # 标记为未连接
            self._reconnect()  # 调用重连方法

    def _on_publish(self, client, userdata, mid):
        """发布回调函数"""
        self.logger.info("已发布 Payload 到 '{}'，mid = {}".format(self.topic, mid))

    def _on_message(self, client, userdata, msg):
        """消息回调函数"""
        data = json.loads(msg.payload.decode())
        self.transfer.put(data)

    def _on_subscribe(self,
                      client,
                      userdata,
                      mid,
                      granted_qos,
                      properties=None):
        """订阅回调函数"""
        self.logger.info("从 '{}' 订阅消息".format(self.topic))

    def _set_will(self, payload):
        """设置遗嘱消息（必须在 connect() 前调用）
        当客户端意外断开时，代理将发布此消息

        :payload: 消息内容
        """
        if self._connected:
            note = "必须在建立连接前设置遗嘱消息"
            self.logger.error(note)
            raise RuntimeError(note)

        self.client.will_set(self.topic_will, payload, self.qos, retain=True)

    def _connect(self):
        """连接 MQTT 服务器"""
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        if self.tls_ca_certs:
            self.client.tls_set(ca_certs=self.tls_ca_certs)

        #  设置遗嘱消息
        self._set_will("客户端 {} 已断开连接".format(self.client_id))

        try:
            self.client.connect(self.host, self.port, self.keepalive)
        except RuntimeError as e:
            self.logger.error("MQTT 配置错误: {}".format(e))
            self.stop()
        except Exception as e:
            self.logger.error("MQTT 连接失败: {}".format(e))
            self.stop()

        self._connected = True
        self.client.loop_start()  # 启动后台线程处理网络流量

    def _reconnect(self):
        """尝试重新连接 MQTT 服务器"""
        try:
            self.logger.info("尝试重新连接到 MQTT 服务器...")
            self.client.reconnect()
            self._connected = True  # 如果成功，标记为已连接
            self.logger.info("重新连接成功")
        except Exception as e:
            self.logger.error("重新连接失败: {}".format(e))

    def stop(self):
        """安全断开连接并清理资源"""
        if self._connected:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False
            self.logger.info('已关闭和 MQTT 服务器的连接')

    def sender(self, data: dict):
        """发布消息到 MQTT

        :data: 消息内容
        """
        payload = json.dumps(data)

        self.client.publish(self.topic,
                            payload,
                            qos=self.qos,
                            retain=self.retain)

    def receiver(self):
        """从 MQTT 订阅消息"""
        self.client.subscribe(self.topic, self.qos)
