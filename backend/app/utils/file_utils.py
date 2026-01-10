import os
from pathlib import Path
from typing import Optional

def _get_project_root() -> Path:
    """Resolve project root. Can be overridden with PROJECT_ROOT env var."""
    env_root = os.getenv("PROJECT_ROOT")
    return Path(env_root).resolve() if env_root else Path.cwd()

def save_temp_file(content: bytes, filename: str, temp_dir: Optional[str] = None) -> str:
    """Save bytes content to a temporary file.Returns the absolute path to the saved file."""
    # 获取项目根目录
    project_root = _get_project_root()
    # 确定临时目录，默认使用项目根目录下的 temp 文件夹
    if not temp_dir:
        temp_dir = project_root / "temp"
    # 如果临时目录不存在，则创建
    os.makedirs(temp_dir, exist_ok=True)
    # 拼接完整的文件路径
    temp_file_path = os.path.join(temp_dir, filename)
    # 写入文件内容
    with open(temp_file_path, 'wb') as f:
        f.write(content)
    # 返回文件的绝对路径
    return temp_file_path