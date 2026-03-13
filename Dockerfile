# ── Stage 1: 编译依赖 ──────────────────────────────────────
FROM python:3.10-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev gcc pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: 运行镜像 ──────────────────────────────────────
FROM python:3.10-slim

LABEL org.opencontainers.image.source=https://github.com/kisen9102-lgtm/dbquery

WORKDIR /app

# 从编译阶段复制已安装的包（不含 gcc 等编译工具）
COPY --from=builder /install /usr/local

# 拷贝项目代码
COPY . .

RUN mkdir -p logs

EXPOSE 8000

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
