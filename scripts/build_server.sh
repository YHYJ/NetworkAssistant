#!/usr/bin/env bash

: <<!
Name: build_server.sh
Author: YJ
Email: yj1516268@outlook.com
Created Time: 2025-10-17 10:37:32

Description: 针对目标机器 glibc 版本过低使用 Docker 容器打包

Attentions:
- Debian 10 (glibc 2.28) 的 Python 镜像对应 glibc 2.28

Depends:
-
!

IMAGE="python:3.9-buster"

echo "正在使用镜像: $IMAGE"

# 获取项目根目录（即 server.py 所在目录）
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "项目根目录: $PROJECT_ROOT"
echo "当前脚本位置: $(dirname "$(readlink -f "$0")")"

HOST_UID=1000

docker run --rm \
  -v "$PROJECT_ROOT":/build \
  -w /build \
  "$IMAGE" \
  bash -c "
    set -e
    pip install --no-cache-dir -i https://mirrors.bfsu.edu.cn/pypi/web/simple pyinstaller
    pip install --no-cache-dir -i https://mirrors.bfsu.edu.cn/pypi/web/simple -r requirements/requirements-server.txt
    pyinstaller --onefile --clean server.py

    # 删除 build 目录
    rm -rf build/
    # 将 dist/ 及其内容的所属用户改为 1000
    chown -R $HOST_UID:$HOST_UID dist/

    echo '✅ 打包完成！二进制文件位于: dist/server'
  "
