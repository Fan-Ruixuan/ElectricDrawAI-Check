from fastapi import APIRouter
router = APIRouter()

@router.post("/recognize")
def ocr_recognize():
    return {"message": "OCR 功能待开发"}