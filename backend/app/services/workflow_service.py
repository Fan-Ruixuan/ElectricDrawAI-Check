import os
import tempfile
import json
import pandas as pd
from app.services.cad_service import cad_to_png  # 已迁移的CAD函数
from app.services.ocr_service import extract_text_from_file  # 已迁移的OCR函数
from app.services.ai_service import call_ai_review  # 已迁移的AI函数

# Demo 里的 _TempUploaded 类
class _TempUploaded:
    def __init__(self, path):
        self.name = os.path.basename(path)
        with open(path, 'rb') as f:
            self._data = f.read()

    def getbuffer(self):
        return self._data

# Demo 里的核心业务逻辑（无任何 Streamlit 代码）
def run_review_workflow(uploaded_file):
    # 1. 判断文件类型，CAD转PNG
    file_ext = uploaded_file.name.split('.')[-1].lower()
    processed_file = uploaded_file
    if file_ext in ['dwg', 'dxf']:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_cad:
            tmp_cad.write(uploaded_file.getbuffer())
            temp_cad_path = tmp_cad.name
        try:
            png_path = cad_to_png(temp_cad_path)
            processed_file = _TempUploaded(png_path)
        finally:
            if os.path.exists(temp_cad_path):
                os.remove(temp_cad_path)

    # 2. OCR提取文本
    extracted_text = extract_text_from_file(processed_file)
    
    # 3. AI审查
    review_result = call_ai_review(extracted_text, drawing_name=uploaded_file.name)
    
    # 4. 返回结果（和 Demo 逻辑一致，暂时不解析）
    return extracted_text, review_result