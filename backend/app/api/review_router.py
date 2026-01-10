from fastapi import APIRouter

router = APIRouter()

# =AI审查接口
@router.post("/analyze")
def review_analyze():
    return {"message": "AI审查功能待开发"}

all = ["router"]    