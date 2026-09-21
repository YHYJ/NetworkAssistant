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
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from utils.other import as_int, turntable


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
        self.port = as_int(config.get('port', 1883), 1883, 'mqtt.port', logger)
        self.username = config.get('username', None)
        self.password = config.get('password', None)
        self.client_id = config.get('client_id', None)
        self.qos = as_int(config.get('qos', 1), 1, 'mqtt.qos', logger)
        if self.qos not in (0, 1, 2):
            logger.warning('mqtt.qos 应为 0/1/2，实际为 {!r}，按 1 处理'.format(
                self.qos))
            self.qos = 1
        self.keepalive = as_int(config.get('keepalive', 60), 60,
                                'mqtt.keepalive', logger)
        self.retain = config.get('retain', False)
        self.tls_ca_certs = config.get('tls_ca_certs', None)
        # 等待下限 1 秒，避免忙循环
        self.wait = max(as_int(config.get('wait', 5), 5, 'mqtt.wait', logger),
                        1)
        self.clean_session = config.get('clean_session', True)

        # Topic
        self.topic = config.get('topic', '/FROM/Gateway/Info')
        self.topic_will = config.get('topic_will', 'status/offline')

        # 需要恢复订阅的 Topic：clean_session 为 True 时，重连后订阅不会自己回来
        self._sub_topics = set()
        self._sub_lock = threading.Lock()

        self._connected = False  # 标记连接状态
        self._stopping = threading.Event()  # 停机信号：置位后不再重连
        self._loop_thread = None  # MQTT 网络循环监督线程
        self._connected_event = threading.Event()  # 连接建立通知
        self._published_event = threading.Event()  # 发布确认通知

        # Client ID 未设置时自动生成
        if not self.client_id:
            self.client_id = turntable()

        # 使用 VERSION2 回调 API
        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=self.clean_session,
        )

        # 设置回调函数
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe

        # 连接异常断开后由 loop_forever 自动重连，重连间隔从 wait 开始指数退避；
        # wait 同时是监督线程兜底重连的等待间隔（下限 1 秒，见上）
        self.client.reconnect_delay_set(min_delay=self.wait, max_delay=120)

        # 连接 MQTT
        self._connect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """连接回调函数
        运行在网络循环线程中，异常不能逃逸出去，否则网络循环会退出

        :reason_code: 连接结果
        """
        try:
            if self._stopping.is_set():
                # 停机过程中才建立起来的连接：立即断开，让 loop_forever 退出
                client.disconnect()
                return

            if reason_code == 0:
                self._connected = True
                self._connected_event.set()
                self.logger.info("已连接 MQTT，客户端 ID = {}".format(self.client_id))
                # clean_session 为 True 时，重连后需要恢复订阅
                self._resubscribe()
            else:
                self._connected = False
                self._connected_event.clear()
                self.logger.error(
                    "连接 MQTT 失败，reason_code = {}".format(reason_code))
        except Exception as e:
            # 连上了却恢复订阅失败 = 收不到消息：断开连接，交由监督线程重连后重试
            self.logger.exception('连接回调异常，断开连接等待重连: {}'.format(e))
            self._disconnect_quietly()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """断开连接回调函数 —— 只记录状态，重连由 loop_forever 负责
        运行在网络循环线程中，异常不能逃逸出去，否则网络循环会退出

        :reason_code: 断开原因
        """
        try:
            # 同一次断开可能被回调两次：disconnect() 写包时同步一次，网络循环线程处理关闭时再一次
            # 只在"从已连接变为断开"时记一条
            was_connected = self._connected
            self._connected = False
            self._connected_event.clear()
            if reason_code == 0:
                if was_connected:
                    self.logger.info("已正常断开与 MQTT 服务器的连接")
            else:
                self.logger.warning(
                    "与 MQTT 服务器连接断开，reason_code = {}，将自动重连".format(
                        reason_code))
        except Exception as e:
            self.logger.exception('断开回调异常: {}'.format(e))

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        """发布回调函数
        运行在网络循环线程中，异常不能逃逸出去，否则网络循环会退出

        :mid: 消息 ID
        """
        try:
            self.logger.info("已发布 Payload 到 '{}'，mid = {}".format(
                self.topic, mid))
            self._published_event.set()  # 通知 sender() 本次发布已被确认
        except Exception as e:
            self.logger.exception('发布回调异常: {}'.format(e))

    def _on_message(self, client, userdata, msg):
        """消息回调函数
        运行在网络循环线程中，异常不能逃逸出去，否则网络循环会退出

        :msg: MQTT 消息
        """
        try:
            data = json.loads(msg.payload.decode())
        except (ValueError, UnicodeDecodeError) as e:
            self.logger.error("解析消息失败: {}，payload = {!r}".format(
                e, msg.payload))
            return

        if not isinstance(data, dict):
            self.logger.error("消息格式错误: payload = {!r}".format(msg.payload))
            return

        try:
            # 用 put_nowait 避免因队列满而阻塞网络循环线程
            self.transfer.put_nowait(data)
        except Exception as e:
            self.logger.error("写入中转站失败: {}".format(e))
            return

        self.logger.info("收到来自 '{}' 的消息".format(msg.topic))

    def _on_subscribe(self, client, userdata, mid, reason_code_list,
                      properties):
        """订阅回调函数
        运行在网络循环线程中，异常不能逃逸出去，否则网络循环会退出

        :mid: 订阅请求的消息 ID
        :reason_code_list: 各 Topic 的订阅结果
        """
        try:
            for reason_code in reason_code_list:
                if reason_code.is_failure:  # 例如权限不足
                    self.logger.error("订阅 '{}' 失败，reason_code = {}".format(
                        self.topic, reason_code))
                    return

            self.logger.info("从 '{}' 订阅消息".format(self.topic))
        except Exception as e:
            self.logger.exception('订阅回调异常: {}'.format(e))

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
        """连接 MQTT 服务器
        非阻塞：连接建立与断开后的自动重连由 loop_forever 完成，
        网络循环意外退出后的兜底重连由监督线程完成
        """
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        if self.tls_ca_certs:
            self.client.tls_set(ca_certs=self.tls_ca_certs)

        #  设置遗嘱消息
        self._set_will("客户端 {} 已断开连接".format(self.client_id))

        try:
            # 用 connect_async 避免连接失败时阻塞初始化流程
            self.client.connect_async(self.host, self.port, self.keepalive)
        except Exception as e:
            self.logger.error("MQTT 配置错误: {}".format(e))
            return

        self._loop_thread = threading.Thread(target=self._loop_supervisor,
                                             name="MQTT-Loop",
                                             daemon=True)
        self._loop_thread.start()

    def _loop_supervisor(self):
        """网络循环监督线程

        loop_forever 自己负责网络断开后的重连；只有它意外退出（回调异常等）才由
        本线程接管 —— 如果没有接管，进程还活着、MQTT 却已经聋了，而且 paho 的
        连接视图与遗嘱语义都已失真（代理侧仍认为客户端在线）。
        """
        while True:
            self._run_loop_forever()  # 阻塞，直到断开或异常退出
            if self._stopping.is_set():
                return
            self.logger.error("MQTT 网络循环已退出，{} 秒后重连".format(self.wait))
            if self._stopping.wait(self.wait):  # 等待期间收到停机信号
                return
            try:
                # 复用同一个 client：重连后 _on_connect 会恢复订阅
                result = self.client.reconnect()
                if result != mqtt.MQTT_ERR_SUCCESS:
                    self.logger.error("重连 MQTT 失败: {}".format(
                        mqtt.error_string(result)))
            except Exception as e:
                self.logger.exception('重连 MQTT 异常: {}'.format(e))

    def _run_loop_forever(self):
        """阻塞运行 MQTT 网络循环（由监督线程调用）"""
        try:
            # loop_forever 会阻塞；断开后自动重连，直到调用 disconnect()
            self.client.loop_forever(retry_first_connection=True)
        except Exception as e:
            self.logger.exception("MQTT 网络循环异常退出: {}".format(e))
        finally:
            self._connected = False
            self._connected_event.clear()

    def _resubscribe(self):
        """重连成功后恢复订阅的 Topic"""
        with self._sub_lock:
            topics = list(self._sub_topics)

        for topic in topics:
            self.logger.info("重新订阅 '{}'".format(topic))
            self._subscribe(topic)

    def _subscribe(self, topic):
        """订阅 Topic

        :topic: 要订阅的 Topic
        :return: subscribe() 的返回码
        """
        result, _ = self.client.subscribe(topic, self.qos)
        if result == mqtt.MQTT_ERR_NO_CONN:
            # 尚未连接：连接建立后由 _resubscribe 订阅，属于正常时序
            self.logger.info("尚未连接 MQTT，'{}' 将在连接建立后订阅".format(topic))
        elif result != mqtt.MQTT_ERR_SUCCESS:
            self.logger.warning("订阅 '{}' 失败: {}".format(
                topic, mqtt.error_string(result)))

        return result

    def _disconnect_quietly(self):
        """断开连接，失败只记日志（停机与回调自愈路径共用）"""
        try:
            self.client.disconnect()
        except Exception as e:
            self.logger.error("断开 MQTT 连接失败: {}".format(e))

    def stop(self):
        """安全停止，disconnect 会让 loop_forever 退出并清理资源"""
        self._stopping.set()  # 停机后建立起来的连接由 _on_connect 立即断开

        self._disconnect_quietly()

        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=self.wait + 1)
            if self._loop_thread.is_alive():
                self.logger.warning("MQTT 网络循环线程未能在 {} 秒内退出".format(self.wait +
                                                                    1))

        if self._connected:
            self.logger.info('已关闭和 MQTT 服务器的连接')
        self._connected = False
        self._connected_event.clear()

    def sender(self, data: dict):
        """发布消息到 MQTT，并等待代理确认

        :data: 消息内容
        :return: 是否已确认送达
        """
        # 一次性客户端（client.py）不会等连接建立，这里替它等
        if not self._connected_event.wait(self.wait):
            self.logger.error("未能在 {} 秒内连上 MQTT，本次消息未发布".format(self.wait))
            return False

        payload = json.dumps(data)
        self._published_event.clear()

        result = self.client.publish(self.topic,
                                     payload,
                                     qos=self.qos,
                                     retain=self.retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            # 未连接但 QoS > 0：消息会进入 paho 的发送队列，连接恢复后自动补发
            if result.rc == mqtt.MQTT_ERR_NO_CONN and self.qos > 0:
                self.logger.warning("连接已断开，消息已排队等待补发: {}".format(self.topic))
            else:
                self.logger.error("发布消息到 '{}' 失败: {}".format(
                    self.topic, mqtt.error_string(result.rc)))
                return False

        # QoS 0 时 paho 在写包时就触发本回调，语义是"已提交"；
        # QoS >= 1 才是代理确认（实测两者停机后都能送达）
        if self._published_event.wait(self.wait):
            return True

        self.logger.error("发布未在 {} 秒内得到代理确认，消息可能未送达 '{}'".format(
            self.wait, self.topic))
        return False

    def receiver(self):
        """从 MQTT 订阅消息（未连接时先记账，连接建立后由 _resubscribe 完成）"""
        with self._sub_lock:
            self._sub_topics.add(self.topic)

        self._subscribe(self.topic)
