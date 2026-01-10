from celery import Celery
from app.core.config import settings

print("REDIS_URL:", settings.REDIS_URL)
print("CELERY_TASK_TIME_LIMIT:", settings.CELERY_TASK_TIME_LIMIT)
# 初始化Celery实例
celery_app = Celery(
    "drawing_review_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.cad_tasks"]  # 任务所在的模块路径
)

# 配置Celery
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    worker_concurrency=4,  # 工作进程数，可根据CPU核心调整
)