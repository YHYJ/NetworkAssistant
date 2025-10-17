# README

<!-- File: README.md -->
<!-- Author: YJ -->
<!-- Email: yj1516268@outlook.com -->
<!-- Created Time: 2025-10-17 10:03:26 -->

---

## Table of Contents

<!-- vim-markdown-toc GFM -->

* [概述](#概述)
* [功能](#功能)
* [编译](#编译)

<!-- vim-markdown-toc -->

---

<!-- Object info -->

---

## 概述

- NetworkAssistant 采用 CS 架构
- server.py 和 client.py 是两个主要文件，统一由 conf/app.toml 配置

## 功能

- client.py 获取指定网络接口的信息并发布到 MQTT
- server.py 从 MQTT 订阅各客户端发布的网络接口信息
- conf/app.toml 是配置文件

## 编译

```bash
pyinstaller --onefile server.py
pyinstaller --onefile client.py
```
