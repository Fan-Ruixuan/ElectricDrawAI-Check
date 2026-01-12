import re
from typing import Dict, Any, Optional
from .data_models import OCRResult

def process_ocr_for_ai(ocr_result: OCRResult, base_prompt: str) -> str:
    """
    处理OCR结果，为AI审查准备最终的提示词
    :param ocr_result: OCR识别结果
    :param base_prompt: AI审查的基础提示词
    :return: 最终拼接好的提示词
    """
    if ocr_result.status != "success":
        raise ValueError(f"OCR识别失败: {ocr_result.error_message}")
    
    # 1. 清洗OCR文本
    cleaned_text = clean_ocr_text(ocr_result.content)
    
    # 2. 从OCR文本中提取关键信息（如图纸编号、比例等）
    extracted_info = extract_key_info(cleaned_text)
    
    # 3. 拼接最终提示词
    final_prompt = build_final_prompt(base_prompt, cleaned_text, extracted_info)
    
    return final_prompt

def clean_ocr_text(text: str) -> str:
    """清洗OCR识别出的文本，去除噪音"""
    # 去除多余的换行和空格
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\s+', ' ', text)
    
    # 去除可能的乱码或特殊字符（保留中文、英文、数字和常用符号）
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\.\,\:\;\(\)\[\]\-\_\+\=\@\#\$\%\^\&\*\!]', '', text)
    
    return text.strip()

def extract_key_info(text: str) -> Dict[str, Any]:
    """从文本中提取关键信息，如图纸编号、比例等"""
    info = {}
    
    # 提取图纸编号（示例正则，可根据实际格式调整）
    drawing_number_pattern = r'([A-Z]{2}-\d{4}-\d{3}-V\d+\.\d+)'
    match = re.search(drawing_number_pattern, text)
    if match:
        info["drawing_number"] = match.group(1)
    
    # 提取图纸比例（示例正则）
    scale_pattern = r'比例\s*[:：]\s*(\d+\s*:\s*\d+)'
    match = re.search(scale_pattern, text)
    if match:
        info["scale"] = match.group(1)
    
    # 可以继续添加其他关键信息的提取规则...
    
    return info

def build_final_prompt(base_prompt: str, cleaned_text: str, extracted_info: Dict[str, Any]) -> str:
    """构建最终的AI提示词"""
    # 拼接提取到的关键信息
    info_str = ""
    if extracted_info:
        info_str = "已知图纸关键信息：\n"
        for key, value in extracted_info.items():
            info_str += f"- {key}: {value}\n"
        info_str += "\n"
    
    # 拼接最终提示词
    final_prompt = f"{base_prompt}\n\n{info_str}待审查的图纸内容如下：\n{cleaned_text}"
    
    return final_prompt