from celery import Celery
from app.core.config import settings

print("REDIS_URL:", settings.REDIS_URL)
print("CELERY_TASK_TIME_LIMIT:", settings.CELERY_TASK_TIME_LIMIT)

# 初始化Celery实例
celery_app = Celery(
    "drawing_review_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.cad_tasks", "app.tasks.ocr_tasks","app.tasks.review_tasks"]  # 任务所在的模块路径
)

# 配置Celery
celery_app.conf.update(
    # 1. 支持字节数据序列化（DWG转图片返回bytes）
    task_serializer="msgpack",
    result_serializer="msgpack",
    accept_content=["json", "msgpack"],  
    result_accept_content=["msgpack"],
    # 2. 时区和UTC对齐（避免时间混乱）
    timezone='Asia/Shanghai',
    enable_utc=False,  # 和本地时区一致
    # 原有配置保留+优化
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    worker_concurrency=4
)