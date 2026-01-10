from fastapi import APIRouter, File, UploadFile, HTTPException
from app.services.ocr_service import perform_ocr_service

router = APIRouter()

@router.post("/recognize")
async def ocr_recognize(file: UploadFile = File(...)):
    """
    测试专用接口：上传一张图片/PDF/DXF/DWG格式，返回OCR识别结果
    """
    try:
        # 读取上传的文件内容
        file_content = await file.read()
        # 识别文件类型
        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            file_type = "pdf"
        elif filename.endswith('.dxf'):
            file_type = "dxf"
        elif filename.endswith('.dwg'):
            file_type = "dwg"
        else:
            file_type = "image"

        # 调用OCR服务
        result = perform_ocr_service(file_content, file_type)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")