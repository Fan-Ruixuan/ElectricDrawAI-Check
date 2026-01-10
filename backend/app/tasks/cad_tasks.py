# CAD 相关的异步任务,导入自己的celery_app实例
from app.core.celery_config import celery_app
from app.services.cad_service import convert_dwg_to_dxf_from_bytes

# 导入公共任务
from .common_tasks import perform_ocr, ai_review, generate_report

from app.services.cad_service import process_image_service
from app.services.cad_service import process_dxf_service
from app.core.celery_config import celery_app

@celery_app.task (bind=True)

def process_image_file (self, file_content: bytes, filename: str) -> dict:
    """处理图片文件的 Celery 任务"""
    # 直接调用服务层的业务逻辑
    return process_image_service (file_content, filename)


@celery_app.task (bind=True)

def process_dwg_file (self, file_content: bytes, filename: str) -> dict:
    """处理 DWG 文件：先转成 DXF，再进行后续处理"""
    try:
        # 第一步：调用 ODA 将 DWG 转为 DXF
        dxf_result = convert_dwg_to_dxf_from_bytes(file_content, filename)
        dxf_file_path = dxf_result["dxf_file"]
        with open(dxf_file_path,'rb') as f:
            dxf_content = f.read()
        # 第二步：将 DXF 内容传给 DXF 处理函数
        return process_dxf_file (dxf_content, filename)
    except Exception as e:
        return {
            "status": "failed",
            "error": str (e),
            "message": "DWG 文件处理失败"
        }

@celery_app.task (bind=True)
def process_dxf_file (self, file_content: bytes, filename: str) -> dict:
    """处理 DXF 文件：进行 OCR 和 AI 审查"""
    # 调用服务层的业务逻辑
    return process_dxf_service(file_content, filename)
   

@celery_app.task (bind=True)
def process_pdf_file (self, file_content: bytes, filename: str) -> dict:
    """处理 PDF 文件：提取图片后进行 OCR 和 AI 审查"""
    return process_pdf_service(file_content, filename)
    

@celery_app.task (bind=True)
def process_image_file (self, file_content: bytes, filename: str) -> dict:
    """处理图像文件：进行 OCR 和 AI 审查"""
    return process_image_service (file_content, filename)
   



