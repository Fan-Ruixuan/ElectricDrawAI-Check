import logging
import io
from pathlib import Path
from PIL import Image
from app.services.cad_service import render_cad_to_image, CADRenderError
from pdf2image import convert_from_bytes
from app.core.config import settings

logger = logging.getLogger(__name__)

class FileConverterService:
    """文件转PNG统一服务：支持DWG/DXF/PDF/图片"""
    def __init__(self):
        self.supported_types = ["dwg", "dxf", "pdf", "jpg", "jpeg", "png"]

    def validate_file_type(self, file_suffix: str) -> bool:
        if file_suffix not in self.supported_types:
            raise ValueError(f"不支持的文件类型！仅支持：{self.supported_types}")
        return True

    def convert_to_png(self, file_content: bytes, file_suffix: str) -> bytes:
        """统一转换为PNG二进制"""
        self.validate_file_type(file_suffix)
        
        # CAD文件（DWG/DXF）
        if file_suffix in ["dwg", "dxf"]:
            return render_cad_to_image(file_content, file_suffix)
        
        # PDF文件
        elif file_suffix == "pdf":
            images = convert_from_bytes(
                file_content,
                dpi=300,
                fmt="png",
                poppler_path=getattr(settings, "POPPLER_PATH", None)
            )
            if not images:
                raise Exception("PDF无有效页面")
            img_byte_arr = io.BytesIO()
            images[0].save(img_byte_arr, format='PNG', dpi=(300, 300))
            return img_byte_arr.getvalue()
        
        # 图片文件（JPG/PNG）
        else:
            img = Image.open(io.BytesIO(file_content))
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()

# 创建实例，供路由/服务调用
file_converter_service = FileConverterService()