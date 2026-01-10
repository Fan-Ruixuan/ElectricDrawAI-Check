from app.core.config import settings
from fastapi import APIRouter, File, UploadFile, HTTPException
from app.tasks.cad_tasks import (process_dwg_file, process_dxf_file, process_pdf_file, process_image_file)
router = APIRouter()

# 支持的文件类型和对应的处理任务
SUPPORTED_FILE_TYPES = {
    ".dwg": process_dwg_file,
    ".dxf": process_dxf_file,
    ".pdf": process_pdf_file,
    ".png": process_image_file,
    ".jpg": process_image_file,
    ".jpeg": process_image_file
}

@router.post("/upload_and_process")
async def upload_and_process_file(file: UploadFile = File(...)):
    try:
        # 获取文件后缀
        file_ext = file.filename.lower().split('.')[-1]
        file_ext = f".{file_ext}"
        # 检查文件类型是否支持
        if file_ext not in SUPPORTED_FILE_TYPES:
            raise HTTPException (
                status_code=400,
                detail=f"不支持的文件格式：{file_ext}。目前仅支持 {', '.join (SUPPORTED_FILE_TYPES.keys ())} 格式。"
            )
        # 读取文件内容
        file_content = await file.read()
        # 根据文件类型分发到对应的任务
        task_func = SUPPORTED_FILE_TYPES[file_ext]
        task = task_func.delay(file_content, file.filename)
        # 返回任务ID以供查询
        return {
            "task_id": task.id, 
            "status": "processing",
            "message": "文件转换任务已提交"
        }
    except Exception as e:
        # 打印完整的错误信息到控制台
        import traceback
        raise HTTPException (status_code=500, detail=f"文件转换失败: {str (e)}")

@router.get("/task/{task_id}")

async def get_task_status(task_id: str):
    from celery.result import AsyncResult
    task = AsyncResult(task_id)
    if task.ready ():
        if task.successful ():
            return {
                "task_id": task_id,
                "status": "completed",
                "result": task.result
            }
        else:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str (task.result)
            }
    else:
        return {
            "task_id": task_id,
            "status": "processing",
            "message": "文件正在处理中，请稍后查询"
        }
