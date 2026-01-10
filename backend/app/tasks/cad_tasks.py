# CAD 相关的异步任务,导入自己的celery_app实例
from app.core.celery_config import celery_app
from app.services.cad_service import convert_dwg_to_dxf_from_bytes

# 导入公共任务
from .common_tasks import perform_ocr, ai_review, generate_report

@celery_app.task (bind=True)

def process_dwg_file (self, file_content: bytes, filename: str) -> dict:
    """处理 DWG 文件：先转成 DXF，再进行后续处理"""
    try:
        # 第一步：调用 ODA 将 DWG 转为 DXF
        dxf_result = convert_dwg_to_dxf_from_bytes(file_content, filename)
        dxf_content = dxf_result["dxf_file"]
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
    try:
        # 这里是 DXF 特有的预处理逻辑，比如渲染为图片
        # 先占位，后续完善
        preprocessed_image = file_content
        # 调用公共 OCR 任务
        ocr_result = perform_ocr(preprocessed_image)
        # 调用公共 AI 审查任务
        ai_result = ai_review(ocr_result)
        # 调用公共报告生成任务
        report = generate_report(ai_result, filename)
        return {
            "status": "success",
            "result": {
                "ocr": ocr_result,
                "ai_review": ai_result,
                "report": report
            },
            "message": "DXF 文件处理完成"
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str (e),
            "message": "DXF 文件处理失败"
        }

@celery_app.task (bind=True)

def process_pdf_file (self, file_content: bytes, filename: str) -> dict:
    """处理 PDF 文件：提取图片后进行 OCR 和 AI 审查"""
    try:
        # 这里是 PDF 特有的预处理逻辑，比如提取图片
        # 先占位，后续完善
        extracted_images = [file_content]
        ocr_results = []
        for image in extracted_images:
            ocr_results.append(perform_ocr(image))
        # 调用公共 AI 审查任务
        ai_result = ai_review(ocr_results)
        # 调用公共报告生成任务
        report = generate_report(ai_result, filename)
        return {
            "status": "success",
            "result": {
                "ocr": ocr_results,
                "ai_review": ai_result,
                "report": report
            },
            "message": "PDF 文件处理完成"
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str (e),
            "message": "PDF 文件处理失败"
        }

@celery_app.task (bind=True)

def process_image_file (self, file_content: bytes, filename: str) -> dict:
    """处理图像文件：进行 OCR 和 AI 审查"""
    try:
        # 调用公共 OCR 任务
        ocr_result = perform_ocr(file_content)
        # 调用公共 AI 审查任务
        ai_result = ai_review(ocr_result)
        # 调用公共报告生成任务
        report = generate_report(ai_result, filename)
        return {
            "status": "success",
            "result": {
                "ocr": ocr_result,
                "ai_review": ai_result,
                "report": report
            },
            "message": "图片文件处理完成"
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str (e),
            "message": "图片文件处理失败"
        }



