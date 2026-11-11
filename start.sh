#!/bin/bash
# 作业任务清单 · 一键启动（Mac / Linux / Termux）
# 用法：
#   ./start.sh            # 用数据库里配置的端口（默认8000）
#   ./start.sh 9000       # 临时指定端口
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python

PORT_ARG=""
if [ -n "$1" ]; then
  PORT_ARG="--port $1"
fi

echo "启动作业任务清单服务…"
exec $PY app.py $PORT_ARG
