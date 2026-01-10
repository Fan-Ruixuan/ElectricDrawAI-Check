from pydantic import BaseModel
from enum import Enum

# 任务状态枚举
class TaskStatusEnum(str, Enum):
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"

# CAD转换响应模型（接口返回给前端的数据格式）
class CADConvertResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum
    message: str = "任务已提交，正在处理中"

# 任务状态查询响应模型
class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum
    result: dict | None = None  # 处理成功时返回结果，失败时返回None