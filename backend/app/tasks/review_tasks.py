# app/tasks/review_tasks.py
from app.core.celery_config import celery_app
from app.services.ai_service import AIService  # 你的AI服务
from app.services.pdf_service import generate_review_pdf  # 你的PDF服务
from app.utils.data_processor import process_ocr_for_ai  # 你的OCR处理工具

from app.utils.prompt_utils import load_prompts_from_text_file, get_prompt_by_drawing_name  # 你的提示词工具
import logging

logger = logging.getLogger(__name__)
ai_service = AIService()  # 初始化AI服务


# 定义异步任务：AI审查+PDF生成
@celery_app.task(bind=True, retry_backoff=3, retry_kwargs={"max_retries": 2})
def async_ai_review(self, ocr_content, drawing_name, model_name, generate_pdf):
    try:
        # 1. 加载提示词（和你原逻辑一致）
        try:
            prompt_dict = load_prompts_from_text_file()
            base_prompt = get_prompt_by_drawing_name(drawing_name or "通用图纸", prompt_dict)
        except Exception:
            # 兜底提示词（用你原来的）
            base_prompt = """请作为专业工程师审查图纸，输出：总体结论、图纸编号、比例、设备型号、技术参数、信息完整性、整改建议"""
        
        # 2. 处理OCR文本生成最终prompt
        # 模拟OCRResult对象（只需要content字段）
        ocr_result = type('OCRResult', (object,), {"content": ocr_content,"status":"success"})()
        final_prompt = process_ocr_for_ai(ocr_result, base_prompt)
        
        # 3. 调用AI服务（指定模型）
        ai_response = ai_service.call_ai(final_prompt, model_name=model_name)
        if ai_response["status"] == "failure":
            raise Exception(ai_response["content"])
        
        # 4. 生成PDF（如果需要）
        pdf_path = None
        if generate_pdf:
            pdf_review_result = {"structured_data": ai_response["content"]}
            pdf_path = generate_review_pdf(pdf_review_result, filename=drawing_name)
        
        # 返回任务结果（和原接口格式对齐）
        return {
            "content": ai_response["content"],
            "model_used": ai_response["model_used"],
            "pdf_path": pdf_path
        }
    except Exception as e:
        logger.error(f"异步任务失败：{str(e)}", exc_info=True)
        # 只重试2次，超过后抛出异常（让任务标记为FAILURE）
        if self.request.retries < self.max_retries:
            self.retry(exc=e)
        else:
            raise Exception(f"任务重试{self.max_retries}次仍失败：{str(e)}")