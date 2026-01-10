import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # 项目基础配置
    PROJECT_NAME: str = "电气图纸审查AI助手"
    API_V1_STR: str = "/api/v1"

    # PostgreSQL数据库配置
    POSTGRES_USER: str 
    POSTGRES_PASSWORD: str 
    POSTGRES_SERVER: str 
    POSTGRES_PORT: int 
    POSTGRES_DB: str 

    # Redis配置（Celery消息队列 + 缓存）
    REDIS_HOST: str 
    REDIS_PORT: int 
    REDIS_DB: int 

    @property
    def DATABASE_URL(self):
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def REDIS_URL(self):
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


    # ODA转换器路径（解耦硬编码，替换为你的实际路径）
    ODA_CONVERTER_PATH: str 
    CAD_RENDER_DPI: int = 300  # 默认高精度DPI
    ODA_TARGET_VERSION: str 
    ODA_INPUT_FORMAT: str 
    ODA_OUTPUT_FORMAT: str 
    ODA_OTHER_PARAM_1: str = "0"
    ODA_OTHER_PARAM_2: str = "1"
    CAD_RENDER_DPI: int = 300  # 高精度渲染DPI
    CAD_RENDER_FIGSIZE: tuple = (20, 20)  # 更大的画布尺寸    

    # Celery配置
    CELERY_TASK_TIME_LIMIT: int = 3600  # 任务超时时间（秒）

    # 百度 OCR 配置
    OCR_API_KEY: str
    OCR_SECRET_KEY: str
    # BAIDU_OCR_ENGINE_PATH: str = "./engine"

    # 大模型配置
    ERNIE_API_KEY: str
    ERNIE_API_URL: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# 全局配置实例，其他模块直接导入
settings = Settings()