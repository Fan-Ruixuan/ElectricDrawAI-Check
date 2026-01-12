# backend/tests/test_cad_service.py
import sys
import os
# 解决模块导入问题：将项目根目录加入Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import io
import pytest
from pdf2image import convert_from_bytes
from app.services.cad_service import process_pdf_service  # 现在能正确导入了
from app.services.ocr_service import baidu_ocr
from app.core.config import settings

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="ezdxf")


# 测试用的PDF文件路径（把你的测试PDF放到tests目录下）
TEST_PDF_PATH = os.path.join(os.path.dirname(__file__), "test.pdf")
# poppler路径（从项目配置中读取，或直接写）
POPPLER_PATH = settings.POPPLER_PATH  # 建议把poppler路径配置到settings里


@pytest.fixture
def test_pdf_bytes():
    """夹具：读取测试PDF的二进制内容"""
    with open(TEST_PDF_PATH, "rb") as f:
        return f.read()


def test_pdf_to_image(test_pdf_bytes):
    """单元测试：PDF转图片功能"""
    try:
        images = convert_from_bytes(
            test_pdf_bytes,
            dpi=300,
            fmt="png",
            poppler_path=POPPLER_PATH
        )
        assert len(images) > 0, "PDF转图片失败，未生成任何图片"
        # 验证图片是否有效
        img_byte_arr = io.BytesIO()
        images[0].save(img_byte_arr, format='PNG')
        assert len(img_byte_arr.getvalue()) > 0, "生成的图片为空"
    except Exception as e:
        pytest.fail(f"PDF转图片测试失败：{str(e)}")


def test_ocr_on_pdf_image(test_pdf_bytes):
    """单元测试：PDF转图片后OCR识别"""
    # 先转图片
    images = convert_from_bytes(
        test_pdf_bytes,
        dpi=300,
        poppler_path=POPPLER_PATH
    )
    # 取第一页转字节流，保存为临时文件
    temp_img_path = os.path.join(os.path.dirname(__file__), "temp_test.png")
    images[0].save(temp_img_path, format='PNG')
    
    # 调用OCR
    ocr_result = baidu_ocr(temp_img_path)
    # 验证OCR结果
    assert isinstance(ocr_result, str), "OCR返回结果不是字符串"
    assert len(ocr_result.strip()) > 0, "OCR识别结果为空"
    
    # 清理临时文件
    os.remove(temp_img_path)


def test_process_pdf_service_integration(test_pdf_bytes):
    """集成测试：调用项目中的process_pdf_service"""
    result = process_pdf_service(test_pdf_bytes, filename="test.pdf")
    assert result["status"] == "success", f"PDF处理失败：{result.get('message')}"
    assert "ocr" in result["result"], "处理结果中缺少OCR数据"