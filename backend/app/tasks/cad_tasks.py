import os
import logging
# CAD 相关的异步任务,导入自己的celery_app实例
from app.core.celery_config import celery_app
# 导入服务层核心函数（按需导入，避免冗余）
from app.services.cad_service import (
    convert_dwg_to_dxf_from_bytes,
    process_image_service,
    process_dxf_service,
    process_pdf_service,
    render_cad_to_image  # 新增：导入渲染函数
)

# 初始化logger（解决logger未定义问题）
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== 原有任务函数（不变） ==========
@celery_app.task(bind=True)
def process_image_file(self, file_content: bytes, filename: str) -> dict:
    """处理图片文件的 Celery 任务"""
    try:
        result = process_image_service(file_content, filename)
        return result
    except Exception as e:
        logger.error(f"图片文件任务处理失败：{str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "图片文件处理任务执行失败"
        }

@celery_app.task(bind=True)
def process_dwg_file(self, file_content: bytes, filename: str) -> dict:
    """处理 DWG 文件: 先转成 DXF，再调用DXF服务层处理"""
    try:
        dxf_result = convert_dwg_to_dxf_from_bytes(file_content, filename)
        if dxf_result["status"] != "success":
            return dxf_result

        dxf_file_path = dxf_result["dxf_file"]
        with open(dxf_file_path, 'rb') as f:
            dxf_content = f.read()

        return process_dxf_service(dxf_content, filename)

    except Exception as e:
        logger.error(f"DWG文件任务处理失败：{str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "DWG 文件处理任务执行失败"
        }

@celery_app.task(bind=True)
def process_dxf_file(self, file_content: bytes, filename: str) -> dict:
    """处理 DXF 文件：调用服务层逻辑"""
    try:
        result = process_dxf_service(file_content, filename)
        return result
    except Exception as e:
        logger.error(f"DXF文件任务处理失败：{str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "DXF 文件处理任务执行失败"
        }

@celery_app.task(bind=True)
def process_pdf_file(self, file_content: bytes, filename: str) -> dict:
    """处理 PDF 文件：调用服务层逻辑"""
    try:
        result = process_pdf_service(file_content, filename)
        return result
    except Exception as e:
        logger.error(f"PDF文件任务处理失败：{str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "PDF 文件处理任务执行失败"
        }

# ========== 新增：CAD转图片异步任务（核心） ==========
@celery_app.task(bind=True, time_limit=3600)
def async_render_cad_to_image(self, file_content: bytes, file_type: str):
    """异步渲染CAD为图片（供OCR接口调用）"""
    try:
        return render_cad_to_image(file_content, file_type)
    except Exception as e:
        logger.error(f"异步渲染CAD图片失败：{str(e)}")
        raise e  # 抛出异常，让Celery标记任务失败