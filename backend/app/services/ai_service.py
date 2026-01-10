
from typing import Optional
import os
import requests
from dotenv import load_dotenv
from app.core.config import settings
from app.utils.prompt_utils import load_prompts_from_text_file, get_prompt_by_drawing_name

# 加载环境变量
load_dotenv()


# =============== prompt模板部分 ================



# =============== AI调用部分 ================

def call_ernie_api(prompt):
    api_key = settings.ERNIE_API_KEY
    if not api_key:
        return "【配置错误】请在 .env 文件中设置 ERNIE_API_KEY"

    api_url = settings.ERNIE_API_URL
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


# =============== 审查逻辑部分 ================

# ai_service.py 中的 ai_review_service 函数修改
def ai_review_service(extracted_text, drawing_name: Optional[str] = None):  # 增加默认值
    ERNIE_API_KEY = settings.ERNIE_API_KEY
    """
    调用 AI 模型进行图纸审查（对接 ERNIE 或返回模拟结果）
    """
    # 如果未配置 ERNIE API Key，返回模拟结果用于测试，避免程序报错
    if not ERNIE_API_KEY:
        return {  # 修改返回格式为字典，和其他服务统一
            "status": "success",
            "structured_data": """【模拟审查结果 - 未配置 AI API Key】
### 总体结论：通过
1. 图纸编号：符合规范（示例：EL-2024-001-V1.0）
2. 图纸比例：符合要求（示例：1:100）
3. 设备型号：标注清晰，无缺项
【提示】：请在 .env 文件中配置 ERNIE_API_KEY 以启用真实 AI 审查功能"""
        }

    # 补充默认图纸名称，避免drawing_name为None
    drawing_name = drawing_name or "通用图纸"
    
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
    # 统一返回格式为字典
    return {
        "status": "success",
        "structured_data": review_result
    }

