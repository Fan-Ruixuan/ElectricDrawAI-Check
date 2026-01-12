from fastapi import APIRouter, File, UploadFile, HTTPException
import tempfile
import os
from app.services.ocr_service import perform_ocr_service, extract_text_from_file
# 修正：从已有的CAD tasks导入异步任务（不是cad_service）
from app.tasks.cad_tasks import async_render_cad_to_image
# 新增：导入你已有的celery_app（用于查询任务状态）
from app.core.celery_config import celery_app
from celery.result import AsyncResult

# 步骤1：先定义router变量
router = APIRouter()

# 新增：查询异步任务结果的接口
@router.get("/task/{task_id}")
async def get_ocr_task_result(task_id: str):
    try:
        # 用msgpack反序列化
        task = AsyncResult(task_id, app=celery_app)
        
        if task.state == 'PENDING':
            return {"status": "processing", "message": "CAD文件正在处理中"}
        elif task.state == 'SUCCESS':
            img_bytes = task.result  # msgpack会自动反序列化字节
            file_type = "dwg" if "dwg" in task_id else "dxf"
            ocr_result = perform_ocr_service(img_bytes, file_type)
            return {"status": "success", "task_id": task_id, "ocr_result": ocr_result}
        elif task.state == 'FAILURE':
            return {"status": "failed", "task_id": task_id, "error": str(task.result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

# 步骤2：OCR识别主接口
@router.post("/recognize")
async def ocr_recognize(file: UploadFile = File(...)):
    try:
        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            # PDF同步处理（不变）
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(await file.read())
                tmp_path = tmp.name
            
            class TempUploadFile:
                def __init__(self, path, name):
                    self.name = name
                    self.path = path
                def getbuffer(self):
                    with open(self.path, "rb") as f:
                        return f.read()
            
            temp_file = TempUploadFile(tmp_path, file.filename)
            text = extract_text_from_file(temp_file)
            os.remove(tmp_path)
            
            return {
                "status": "success" if "[提取失败]" not in text else "failed",
                "structured_data": {
                    "text": text,
                    "file_type": "pdf",
                    "page_count": text.count("=== 第 ")
                }
            }
        else:
            file_content = await file.read()
            if filename.endswith(('.dwg', '.dxf')):
                # DWG/DXF异步处理（调用已有的Celery任务）
                file_type = "dwg" if filename.endswith('.dwg') else "dxf"
                # 触发异步任务
                task = async_render_cad_to_image.delay(file_content, file_type)
                # 返回任务ID
                return {
                    "status": "processing",
                    "task_id": task.id,
                    "file_type": file_type,
                    "message": "CAD文件已提交异步处理，请调用 /task/{task_id} 查询结果"
                }
            else:
                # 普通图片同步处理
                file_type = "image"
                result = perform_ocr_service(file_content, file_type)
                return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")