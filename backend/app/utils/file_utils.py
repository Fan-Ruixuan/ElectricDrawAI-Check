import os
from pathlib import Path
from typing import Optional

# 核心修改：导入cad_service中经过验证的通用保存函数
from app.services.cad_service import universal_save_temp_file

def _get_project_root() -> Path:
    """Resolve project root. Can be overridden with PROJECT_ROOT env var."""
    env_root = os.getenv("PROJECT_ROOT")
    return Path(env_root).resolve() if env_root else Path.cwd()

# 兼容旧代码的调用方式，实际执行统一的保存逻辑
def save_temp_file(content: bytes, filename: str, temp_dir: Optional[str] = None) -> str:
    """
    兼容原有调用，底层使用统一的临时文件保存逻辑
    :param content: 文件二进制内容
    :param filename: 原文件名
    :param temp_dir: 旧逻辑的临时目录参数（兼容用）
    :return: 绝对文件路径
    """
    # 解析子目录（保持和旧逻辑兼容）
    sub_dir = "cad"  # 默认用cad目录
    if temp_dir:
        # 从旧的temp_dir参数中提取子目录名称
        sub_dir = Path(temp_dir).name or sub_dir
    
    # 调用统一的保存函数
    return universal_save_temp_file(content, filename, sub_dir=sub_dir)