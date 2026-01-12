import logging
import io
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional, Dict, Any
from app.core.config import settings
from app.services.ocr_strategy_service import ocr_strategy_service  # 你的OCR模块
from app.tasks.review_tasks import async_ai_review  # AI审查异步任务

# ========== 修复1：正确导入Celery实例 ==========
from app.core.celery_config import celery_app  

# 初始化路由
router = APIRouter()
logger = logging.getLogger(__name__)

# ========== 新增：PDF转图片的依赖（先安装：pip install pdf2image pillow） ==========
try:
    from pdf2image import convert_from_bytes
    from PIL import Image
except ImportError:
    logger.warning("未安装pdf2image/pillow，PDF文件处理功能不可用！请执行：pip install pdf2image pillow")
    convert_from_bytes = None
    Image = None

# 纯异步接口：串联CAD/PDF→OCR→AI审查（支持多文件类型）
@router.post("/analyze")
async def review_analyze(
    file: UploadFile = File(...),  # 支持上传DWG/DXF/PDF文件
    drawing_name: Optional[str] = Form(None),
    model_name: Optional[str] = Form("ernie"),
    generate_pdf: Optional[bool] = Form(True)
) -> Dict[str, Any]:
    # ========== 第一步：识别文件类型，分流处理 ==========
    # 获取文件后缀（小写）
    file_suffix = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    supported_types = ["dwg", "dxf", "pdf"]
    if file_suffix not in supported_types:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型！仅支持：{supported_types}")
    
    # 读取文件二进制内容
    file_content = await file.read()
    png_bytes = None
    
    # 分支1：处理CAD文件（DWG/DXF）
    if file_suffix in ["dwg", "dxf"]:
        try:
            from app.services.cad_service import render_cad_to_image, CADRenderError
            # 用asyncio.to_thread包装同步函数，不阻塞事件循环
            png_bytes = await asyncio.to_thread(
                render_cad_to_image,
                file_content=file_content,
                file_type=file_suffix
            )
            logger.info(f"✅ CAD模块处理完成：{file.filename} 转PNG成功（PNG大小：{len(png_bytes)}字节）")
        except CADRenderError as e:
            logger.error(f"❌ CAD模块处理失败：{str(e)}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"CAD模块处理失败：{str(e)}")
        except Exception as e:
            logger.error(f"❌ CAD模块未知异常：{str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"CAD模块内部错误：{str(e)}")
    
    # 分支2：处理PDF文件
    elif file_suffix == "pdf":
        if not convert_from_bytes or not Image:
            raise HTTPException(status_code=500, detail="缺少PDF处理依赖！请执行：pip install pdf2image pillow")
        try:
            # PDF转图片（取第一页，如需多页可循环处理）
            logger.info(f"开始处理PDF文件：{file.filename}，转换第一页为PNG")
            # 转换PDF字节为PIL图片（Windows需安装poppler，见下方说明）
            images = await asyncio.to_thread(
                convert_from_bytes,
                file_content,
                dpi=300,  # 高清转换，提升OCR准确率
                first_page=1,
                last_page=1
            )
            if not images:
                raise Exception("PDF文件无有效页面")
            
            # PIL图片转二进制字节
            img_byte_arr = io.BytesIO()
            images[0].save(img_byte_arr, format='PNG', dpi=(300, 300))
            png_bytes = img_byte_arr.getvalue()
            logger.info(f"✅ PDF模块处理完成：{file.filename} 转PNG成功（PNG大小：{len(png_bytes)}字节）")
        except Exception as e:
            logger.error(f"❌ PDF模块处理失败：{str(e)}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"PDF模块处理失败：{str(e)}")
    
    # ========== 第二步：调用OCR模块，PNG转文本 ==========
    try:
        # 把PNG二进制包装成UploadFile对象，传给OCR模块
        png_file = UploadFile(
            filename=f"{file.filename}.png",
            file=io.BytesIO(png_bytes)
        )
        # 调用你已有的OCR服务处理PNG
        ocr_result = await ocr_strategy_service.process_file(png_file)
        
        # 校验OCR结果（放宽长度限制，避免小文件报错）
        if ocr_result["status"] != "success":
            raise Exception(ocr_result.get("error_message", "OCR识别失败"))
        # 修复2：放宽文本长度限制（CAD/PDF转PNG后OCR文本可能短）
        if not ocr_result["content"] or len(ocr_result["content"].strip()) < 1:
            raise Exception("OCR识别结果为空")
        
        logger.info(f"OCR模块处理完成：提取文本长度 {len(ocr_result['content'])}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OCR模块处理失败：{str(e)}")

    # ========== 第三步：提交Celery异步任务，AI审查 ==========
    try:
        # 关键：delay()是异步提交的核心，必须保留
        task = async_ai_review.delay(
            ocr_content=ocr_result["content"],
            drawing_name=drawing_name or file.filename,
            model_name=model_name,
            generate_pdf=generate_pdf
        )
        logger.info(f"AI审查任务提交成功，task_id：{task.id}")  # 新增日志，确认提交
    except Exception as e:
        logger.error(f"提交AI审查任务失败：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"提交AI审查任务失败：{str(e)}")

    # 返回任务ID，接口无阻塞
    return {
        "status": "task_submitted",
        "task_id": task.id,
        "message": f"{file_suffix.upper()}→OCR处理完成，AI审查任务已提交（异步执行）",
        "ocr_confidence": ocr_result.get("confidence", "N/A")
    }

# 异步结果查询接口
@router.get("/analyze/result/{task_id}")
async def get_review_result(task_id: str):
    # 修复1：用正确的celery_app实例查询任务
    task = celery_app.AsyncResult(task_id)
    if task.state == "PENDING":
        return {"status": "pending", "message": "任务排队中，暂未执行"}
    elif task.state == "SUCCESS":
        return {
            "status": "success",
            "data": task.result,
            "message": "AI审查完成"
        }
    elif task.state == "FAILURE":
        err_msg = str(task.result) if task.result else "任务执行失败，无具体信息"
        return {"status": "failure", "message": f"任务执行失败：{err_msg}"}
    else:
        return {"status": "running", "message": f"任务执行中，当前状态：{task.state}"}