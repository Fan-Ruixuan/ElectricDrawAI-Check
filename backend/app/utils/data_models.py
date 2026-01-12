from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class OCRResult(BaseModel):
    """OCR识别结果的数据模型"""
    status: str  # success/failure
    content: str  # 识别出的纯文本
    metadata: Dict[str, Any] = {}  # 结构化的元数据，如图纸编号、比例等
    confidence: Optional[float] = None  # 识别的置信度
    error_message: Optional[str] = None  # 错误信息（如果识别失败）

class AIResult(BaseModel):
    """AI审查结果的数据模型"""
    status: str  # success/failure
    content: str  # 审查结果文本
    model_used: Optional[str] = None  # 使用的AI模型名称
    error_message: Optional[str] = None  # 错误信息（如果审查失败）