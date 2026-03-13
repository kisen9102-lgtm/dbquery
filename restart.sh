#!/bin/bash

cd "$(dirname "$0")"

echo "停止旧进程..."
pkill -f "manage.py runserver" 2>/dev/null
sleep 1

echo "启动服务..."
nohup python3 manage.py runserver 0.0.0.0:8000 >> logs/runserver.log 2>&1 &

echo "服务已启动，PID: $!"
echo "日志：logs/runserver.log"
