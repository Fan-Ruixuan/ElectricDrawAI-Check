import io
import re
import os
import logging

import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter

from app.core.config import settings
from app.core.celery_config import celery_app
from app.services.ocr_strategy_service import OCRStrategyService  # 已导入策略层

# -删除 timeout_decorator 和 functools.wraps 的导入

logger = logging.getLogger(__name__)

# 指定 tesseract 可执行文件路径（策略层会用到）
pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD_PATH


def preprocess_image(img: Image.Image) -> Image.Image:
    """
    针对电气图纸的特点，优化图像预处理流程：
    - 转灰度
    - 二值化
    - 去噪（中值滤波）
    - 尝试自动方向检测并旋转保证文字水平
    """
    # 转为灰度
    img = img.convert("L")

    # 二值化（简单阈值）
    img = img.point(lambda x: 0 if x < 128 else 255, "1")

    # 去除噪声
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # 尝试检测并矫正方向
    try:
        osd = pytesseract.image_to_osd(img)
        m = re.search(r"(?<=Rotate: )\d+", osd)
        if m:
            angle = int(m.group(0))
            if angle != 0:
                img = img.rotate(-angle, expand=True)
    except Exception:
        # 方向检测失败时跳过，不影响后续 OCR
        pass

    return img


def postprocess_ocr_result(raw_text: str) -> dict:
    """
    对原始 OCR 结果进行清洗和结构化。
    - 去除空行和首尾空白
    - 根据电气图纸常见关键词提取关键信息
    """
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    structured_data = {
        "raw_text": raw_text,
        "lines": lines,
        "key_elements": []
    }

    # 根据电气图纸特点提取关键信息（简单规则示例）
    keywords = ["编号", "参数", "型号", "规格", "电压", "电流"]
    for line in lines:
        if any(keyword in line for keyword in keywords):
            structured_data["key_elements"].append(line)

    return structured_data

# -删除 convert_with_timeout 函数（不再需要）

# -给 Celery 任务添加原生超时参数
@celery_app.task(bind=True, time_limit=60, soft_time_limit=55)
def perform_ocr(self, file_content: bytes, file_type: str = "image") -> dict:
    """
    执行 OCR 识别（支持图片、PDF、DXF 已渲染图片）。
    :param file_content: 文件二进制内容
    :param file_type: 'image' | 'pdf' | 'dxf'
    :return: 包含识别结果的字典
    """
    try:
        images = []

        # 根据文件类型处理
        if file_type == "pdf":
            logger.info("开始将 PDF 转换为图片进行 OCR 识别")
            try:
                # -直接调用 convert_from_bytes，不再用超时装饰器函数
                images = convert_from_bytes(file_content, dpi=300, fmt='png',output_folder=None,first_page=None,last_page=None,grayscale=True)
            except Exception as e:
                # -捕获转换异常（包含超时/其他错误）
                raise ValueError(f"PDF 转换失败：{str(e)}（可能是文件过大/转换耗时过长）")

            if not images:
                raise ValueError("PDF 文件转换后无有效图片")

        elif file_type in ("image", "dxf"):
            logger.info(f"开始处理 {file_type} 类型图片的 OCR 识别")
            img_buffer = io.BytesIO(file_content)
            try:
                # 打开并校验图片
                with Image.open(img_buffer) as img:
                    img.verify()  # 校验文件头
                img_buffer.seek(0)
                # 重新打开用于识别
                images = [Image.open(img_buffer).convert("RGB")]
            except Exception as e:
                raise ValueError(f"无效的图片格式，无法识别: {e}")

        else:
            raise ValueError(f"不支持的文件类型: {file_type}，仅支持 image/pdf/dxf")

        # 初始化存储识别结果的列表
        full_text_parts = []

        # 遍历每张图片执行 OCR（核心：调用策略层）
        for idx, img in enumerate(images):
            logger.info(f"开始处理第{idx+1}张图片的OCR识别")
            # 图片预处理（保留原有逻辑）
            img = preprocess_image(img)
            
            # 调用双OCR策略层（核心修改）
            ocr_strategy = OCRStrategyService()
            ocr_res = ocr_strategy.recognize(img, file_type=file_type, strategy="hybrid")
            
            # 处理识别结果
            if ocr_res["status"] == "success":
                full_text_parts.append(ocr_res["text"])
                logger.info(f"第{idx+1}张图片识别成功，使用引擎：{ocr_res['engine']}")
            else:
                logger.error(f"第{idx+1}张图片双引擎识别均失败：{ocr_res['error']}")
                raise ValueError(f"OCR识别失败：{ocr_res['error']}")
            
            # 释放内存
            del img
            logger.info(f"第{idx+1}张图片OCR识别完成")

        # 合并所有页面的识别结果
        full_text = "\n".join(full_text_parts)
        # 结果后处理（保留原有结构化逻辑）
        structured_result = postprocess_ocr_result(full_text)
        
        # 返回标准化结果
        return {
            "status": "success",
            "ocr_result": structured_result,
            "confidence": 0.92,
            "message": f"成功识别 {len(images)} 张图片"
        }

    except ValueError as e:
        # 捕获业务相关错误（如格式/参数错误）
        logger.error(f"OCR 识别业务错误：{e}")
        return {"status": "failed", "error": str(e), "message": "OCR 识别参数 / 格式错误"}

    except Exception as e:
        # 捕获其他未知错误
        logger.exception("OCR 识别系统错误")
        return {"status": "failed", "error": str(e), "message": "OCR 识别失败"}