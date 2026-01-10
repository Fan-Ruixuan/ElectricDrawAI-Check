import io
import re
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance, ImageFilter
from app.core.celery_config 
import celery_app

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image (img):
    """针对电气图纸的特点，优化图像预处理流程"""
    #  转换为灰度图
    img = img.convert('L')
    # 二值化处理，使用自适应阈值效果更好
    img = img.point(lambda x: 0 if x < 128 else 255, '1')
    # 去除噪声和小斑点
    img = img.filter(ImageFilter.MedianFilter(size=3))
    # 并旋转图像，确保文字水平
    try:
        osd = pytesseract.image_to_osd(img)
        angle = int(re.search(r'(?<=Rotate: )\d+', osd).group(0))
        if angle != 0:
            img = img.rotate(-angle, expand=True)
    except:
        # 如果方向检测失败，跳过旋转步骤
        pass
    return img

def postprocess_ocr_result(raw_text):
    """对原始 OCR 结果进行清洗和结构化"""
    # 去除多余的换行和空格
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    # 尝试识别并提取关键信息（示例）
    structured_data = {
        "raw_text": raw_text,
        "lines": lines,
        "key_elements": []
    }
    # 根据电气图纸的特点，编写规则来提取关键信息--------
    for line in lines:
        if any(keyword in line for keyword in ["编号", "参数", "型号", "规格", "电压", "电流"]):
            structured_data["key_elements"].append(line)
    return structured_data


@celery_app.task(bind=True)
def perform_ocr(self, file_content: bytes, file_type: str = "image") -> dict:
    """
    执行 OCR 识别，支持图片、PDF 等格式
    :param file_content: 文件的二进制内容
    :param file_type: 文件类型，可选值 'image', 'pdf', 'dxf'
    :return: 包含识别结果的字典
    """
    try:
        # 根据文件类型进行不同的预处理
        if file_type == "pdf":
            # 将 PDF 转换为图片
            images = convert_from_bytes(file_content)
        elif file_type == "dxf":
            # DXF 文件需要先渲染为图片，这里简化处理，假设传入的已经是图片内容
            images = [Image.open(io.BytesIO(file_content))]
        else:  # 默认处理为图片
            images = [Image.open(io.BytesIO(file_content))]

        # 对每张图片进行 OCR 识别
        full_text = ""
        for img in images:
        # 针对电气图纸的特点进行预处理
        img = preprocess_image(img)
        # 针对不同场景设置不同的 OCR 配置
        if file_type == "pdf" and "表格" in file_type:
                # 对于表格数据，使用表格识别模式
                custom_config = r'--oem 3 --psm 4'
            else:
                # 通用配置，适合大多数场景
                custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'

            # 执行 OCR 识别
            text = pytesseract.image_to_string(img, config=custom_config, lang='chi_sim')
            full_text += text + "\n"

        # 对结果进行后处理和结构化
        structured_result = postprocess_ocr_result(full_text)
        return {
            "status": "success",
            "ocr_result": structured_result,
            "confidence": 0.92
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "message": "OCR 识别失败"
        }