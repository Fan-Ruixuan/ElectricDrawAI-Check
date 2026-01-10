from fastapi import FastAPI
from app.api.cad_router import router as cad_router
from app.api.ocr_router import router as ocr_router
from app.api.review_router import router as review_router
from fastapi.staticfiles import StaticFiles # 导入静态文件模块
from fastapi.middleware.cors import CORSMiddleware

# 创建 FastAPI 应用实例
app = FastAPI(title="电气图纸审查AI助手", version="1.0")

# 挂载静态文件目录, 将 /static 路径映射到新建的 static 文件夹
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置 CORS
origins = "http://localhost:3000", # 你的前端地址"http://127.0.0.1:3000",
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册各个功能模块的路由
app.include_router(cad_router, prefix="/api/cad", tags=["CAD处理"])
app.include_router(ocr_router, prefix="/api/ocr", tags=["OCR识别"])
app.include_router(review_router, prefix="/api/review", tags=["AI审查"])

@app.get("/")
async def root():
    return {"message": "电气图纸审查AI助手服务已启动"}