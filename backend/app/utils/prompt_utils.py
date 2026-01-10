

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