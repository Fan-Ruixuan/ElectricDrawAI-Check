
from typing import Optional
import os
import requests
from dotenv import load_dotenv
from app.services.cad_service import convert_dwg_to_dxf_from_path,cad_to_png
import app.core.config import OCR_API_KEY, OCR_SECRET_KEY

# 加载环境变量
load_dotenv()


# =============== prompt模板部分 ================

def load_prompts_from_text_file(file_path: str = "Company Rules") -> dict:
    """
    从名为Company Rules的文本文件中加载图纸类型与对应Prompt的字典
    :param file_path: 文本文件路径，默认同目录下的Company Rules
    :return: 键：图纸类型，值：对应Prompt
    """
    prompt_dict = {}
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        # 按分隔符拆分，获取所有「图纸类型===Prompt」片段
        segments = content.split("===")
        # 第一个元素为空（若文件开头无内容），从第二个元素开始处理
        for i in range(1, len(segments), 2):
            if i + 1 < len(segments):
                drawing_type = segments[i].strip()  # 图纸类型
                prompt = segments[i + 1].strip()    # 对应Prompt
                prompt_dict[drawing_type] = prompt
    return prompt_dict

def get_prompt_by_drawing_name(drawing_name: str, prompt_dict: dict) -> str:
    """
    根据图纸名称从字典中匹配对应Prompt
    :param drawing_name: 图纸文件名或页眉标识（如："XX项目220千伏配电装置平面布置图.dwg"）
    :param prompt_dict: 由load_prompts_from_text_file生成的Prompt字典
    :return: 匹配到的Prompt，未匹配到则返回默认Prompt
    """
    # 默认Prompt：通用电气图纸处理逻辑
    default_prompt = """请完成以下3项任务，基于当前电气图纸的图像内容：
1. **文本提取**：提取所有与电气设计相关的核心字段，提取结果以JSON格式呈现。
2. **问题识别**：排查潜在的设计安全隐患、合规性问题及不合理布局。
3. **改进建议**：针对识别出的问题给出具体改进建议；若无问题，说明设计优势。
要求：结果结构化，分“提取结果”“问题识别”“改进建议”三部分返回。"""
    
    for drawing_type, prompt in prompt_dict.items():
        if drawing_type in drawing_name:
            return prompt
    return default_prompt

# 示例使用
if __name__ == "__main__":
    # 1. 加载Prompt字典
    prompt_dict = load_prompts_from_text_file()
    # 2. 匹配图纸名称对应的Prompt
    test_drawing_name = "XX项目220千伏主变间隔断面图.dwg"
    matched_prompt = get_prompt_by_drawing_name(test_drawing_name, prompt_dict)
    print("匹配到的Prompt：", matched_prompt)



# =============== AI调用部分 ================

    def call_ernie_api(prompt):
    api_key = os.getenv("ERNIE_API_KEY")
    if not api_key:
        return "【配置错误】请在 .env 文件中设置 ERNIE_API_KEY"

    api_url = os.getenv("ERNIE_API_URL")

    request_data = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "model": "ernie-3.5-8k"
    }

    headers = {"Content-Type": "application/json","Authorization": f"Bearer {api_key}"}

    try:
        response = requests.post(api_url, headers=headers, json=request_data, timeout=60)
        response.raise_for_status()
        resp_json = response.json()

        # 解析响应结果
        if isinstance(resp_json, dict):
            if "result" in resp_json:
                return resp_json["result"]
            elif "choices" in resp_json and resp_json["choices"]:
                choice = resp_json["choices"][0]
                return choice.get("message", {}).get("content") or choice.get("text") or str(choice)
            else:
                return f"【AI 返回格式异常】\n{str(resp_json)}"
        else:
            return str(resp_json)

    except Exception as e:
        return f"【调用失败】{str(e)}"

from prompt_utils import load_prompts_from_text_file, get_prompt_by_drawing_name


# =============== 审查逻辑部分 ================

def call_ai_review(extracted_text, drawing_name):
    ERNIE_API_KEY = os.getenv("ERNIE_API_KEY")
    """
    调用 AI 模型进行图纸审查（对接 ERNIE 或返回模拟结果）
    """
    # 如果未配置 ERNIE API Key，返回模拟结果用于测试，避免程序报错
    if not ERNIE_API_KEY:
        return """【模拟审查结果 - 未配置 AI API Key】
### 总体结论：通过
1. 图纸编号：符合规范（示例：EL-2024-001-V1.0）
2. 图纸比例：符合要求（示例：1:100）
3. 设备型号：标注清晰，无缺项
【提示】：请在 .env 文件中配置 ERNIE_API_KEY 以启用真实 AI 审查功能""" 

    # 从 prompt_utils 中加载提示词字典（容错处理）
    try:
        prompt_dict = load_prompts_from_text_file()
    except Exception:
        prompt_dict = {}

    # 根据图纸名称匹配对应的专业提示词（容错）
    try:
        base_prompt = get_prompt_by_drawing_name(drawing_name, prompt_dict)
    except Exception:
        # 回退到通用规则或直接使用 drawing_name 作为提示
        base_prompt = prompt_dict.get("default", "") if isinstance(prompt_dict, dict) else ""
        if not base_prompt:
            base_prompt = drawing_name or ""

    # 拼接最终的 prompt，只添加图纸内容
    prompt = f"{base_prompt}\n\n待审查的图纸内容如下：\n{extracted_text}"

    # 调用 AI 接口并返回结果
    review_result = call_ernie_api(prompt)
    return review_result