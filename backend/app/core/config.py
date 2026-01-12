import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from typing import ClassVar, Tuple
from pydantic import Field  # 新增：导入Field（之前漏了）

# 加载.env文件（优先加载项目根目录的.env）
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

class Settings(BaseSettings):
    # ========== 项目基础配置（ClassVar标记静态变量，不参与.env加载） ==========
    PROJECT_ROOT: ClassVar[Path] = Path(__file__).parent.parent.parent
    PROJECT_NAME: str = "电气图纸审查AI助手"
    API_V1_STR: str = "/api/v1"

    # ========== 临时目录配置（静态变量） ==========
    OCR_TEMP_DIR: ClassVar[str] = os.path.join(PROJECT_ROOT, "temp", "ocr")
    CAD_TEMP_DIR: ClassVar[str] = os.path.join(PROJECT_ROOT, "temp", "cad")  # 补充CAD临时目录

    # ========== CAD渲染配置（统一类型注解，无重复） ==========
    CAD_RENDER_FIGSIZE: Tuple[int, int] = (20, 20)  # 最终生效的配置
    CAD_RENDER_DPI: int = 300

    # ========== 数据库配置（从.env加载，必填） ==========
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str = "localhost"  # 给默认值，避免必填报错
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    # ========== Redis配置（从.env加载） ==========
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ========== 数据库URL（动态属性） ==========
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ========== ODA转换器配置（从.env加载） ==========
    ODA_CONVERTER_PATH: str  # 在.env中配置
    ODA_TARGET_VERSION: str = "ACAD2018"  # 默认值
    ODA_INPUT_FORMAT: str = "DWG"  # 默认值
    ODA_OUTPUT_FORMAT: str = "DXF"  # 默认值
    ODA_OTHER_PARAM_1: str = "0"
    ODA_OTHER_PARAM_2: str = "1"

    # ========== Celery配置（修正：去掉Field，改用动态属性+默认值） ==========
    CELERY_TASK_TIME_LIMIT: int = 3600  # 1小时超时
    # 核心修正：用动态属性复用REDIS_URL，避免冗余
    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL  # 复用Redis配置，无需重复定义
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL  # 和broker一致

    # ========== PDF转图片配置（静态变量） ==========
    POPPLER_PATH: ClassVar[str] = r"D:\\Program Files\\poppler\\poppler-25.12.0\\Library\bin"

    # ========== OCR配置 ==========
    # 百度OCR（必填）
    OCR_APP_ID: str
    OCR_API_KEY: str
    OCR_SECRET_KEY: str
    # Tesseract OCR（静态变量）
    TESSERACT_OEM: ClassVar[int] = 3
    TESSERACT_PDF_PSM: ClassVar[int] = 4
    TESSERACT_IMAGE_PSM: ClassVar[int] = 6
    TESSERACT_PRESERVE_SPACES: ClassVar[bool] = True
    TESSERACT_CMD_PATH: ClassVar[str] = r'd:\Program Files\Tesseract-OCR\tesseract.exe'

    # ========== 大模型配置（从.env加载，规范命名） ==========
    ERNIE_API_KEY: str
    ERNIE_API_URL: str = "https://qianfan.baidubce.com/v2/chat/completions"  # 默认值
    ERNIE_MODEL: str = "ernie-3.5-8k"  # 大写开头，适配.env的ERNIE_MODEL
    
    DASHSCOPE_API_KEY: str
    DASHSCOPE_API_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"  # 默认值
    DASHSCOPE_MODEL: str = "qwen-turbo"  # 大写开头，适配.env的DASHSCOPE_MODEL

    # ========== Pydantic配置 ==========
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # 忽略大小写，ERNIE_MODEL和ernie_model都能识别
        extra="ignore"  # 忽略.env中未定义的字段
    )

# 全局配置实例（其他模块导入这个实例即可）
settings = Settings()