# backend/celery_app.py
from celery import Celery
from app.core.config import settings  # 你的配置文件在app/core/config.py

# 初始化Celery（用Redis做消息队列，默认本地Redis地址）
celery_app = Celery(
    "ai_review",
    broker="redis://localhost:6379/0",  # 本地Redis，生产环境改线上地址
    backend="redis://localhost:6379/0", # 存储任务结果
    include=["app.tasks.review_tasks"]  # 后续要写的异步任务文件
)

# 配置任务超时等参数
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=300,  # 任务最长运行5分钟
    result_expires=3600   # 结果保留1小时
)