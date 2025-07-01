# 使用官方的 Python 3.10-slim-bookworm 镜像作为基础镜像
# slim 版本包含最少的依赖，能有效减小镜像体积，适用于生产环境
FROM python:3.12-slim-bookworm

# 设置环境变量，确保 Python 输出到控制台而不是缓冲，方便日志查看
ENV PYTHONUNBUFFERED 1

# 设置工作目录
WORKDIR /app

# 安装 Poetry，一个现代的 Python 依赖管理和打包工具
# 使用 pip 安装 Poetry，并将其添加到 PATH
RUN pip install poetry==1.8.2 \
    && python -m poetry config virtualenvs.create false \
    && python -m poetry config installer.no-root-file true

# 复制 pyproject.toml 和 poetry.lock (如果存在)
# 这样可以利用 Docker 的缓存机制，如果依赖没有变化，则不需要重新安装
COPY pyproject.toml poetry.lock* /app/

# 安装项目依赖
# --no-root 表示不安装项目本身作为包
# --no-dev 表示不安装开发依赖 (如 pytest)
RUN poetry install --no-root --no-dev

# 复制整个应用程序代码到容器中
# 假设你的所有 Python 模块都在 src/funding_rate_arbitrage_bot 目录下
COPY src/ /app/src/

# 创建一个非 root 用户，并切换到该用户，提高容器安全性
# 避免以 root 用户运行应用程序是最佳实践
RUN adduser --system --group appuser \
    && chown -R appuser:appuser /app

USER appuser

# 暴露应用可能监听的端口 (如果你的应用有 web 接口或需要通过端口通信)
# 虽然你的套利机器人可能不需要直接暴露端口，但作为一个规范化示例，可以保留。
# 例如，如果未来集成一个简单的监控 API。
# EXPOSE 8000

# 定义容器启动时执行的命令
# python -m src.funding_rate_arbitrage_bot.main 表示以模块形式运行 main.py
# 这样可以正确处理相对导入
CMD ["python", "-m", "src.funding_rate_arbitrage_bot.main"]