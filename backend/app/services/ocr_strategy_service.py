import logging
import pytesseract
from PIL import Image
from aip import AipOcr
from app.core.config import settings
import io
from fastapi import UploadFile

logger = logging.getLogger(__name__)

class OCRStrategyService:
    def __init__(self):
        # 初始化百度OCR客户端（读config配置）
        self.baidu_client = AipOcr(
            settings.OCR_APP_ID,
            settings.OCR_API_KEY,
            settings.OCR_SECRET_KEY
        )
        # 初始化Tesseract配置（读config，不用改ocr_tasks里的配置）
        self.tesseract_config = {
            'pdf': f'--oem {settings.TESSERACT_OEM} --psm {settings.TESSERACT_PDF_PSM}',
            'image': f'--oem {settings.TESSERACT_OEM} --psm {settings.TESSERACT_IMAGE_PSM}'
        }
        if settings.TESSERACT_PRESERVE_SPACES:
            for k in self.tesseract_config:
                self.tesseract_config[k] += ' -c preserve_interword_spaces=1'

    async def process_file(self, file: UploadFile) -> dict:
        """
        异步处理上传文件（适配FastAPI的UploadFile）
        :param file: FastAPI上传的文件对象
        :return: 标准化的OCR结果字典（适配OCRResult模型）
        """
        try:
            # 1. 读取上传文件并转换为PIL Image
            file_content = await file.read()
            image = Image.open(io.BytesIO(file_content))
            
            # 2. 判断文件类型（PDF/图片）
            file_suffix = file.filename.split(".")[-1].lower() if "." in file.filename else ""
            if file_suffix == "pdf" or file.content_type == "application/pdf":
                file_type = "pdf"
            else:
                file_type = "image"
            
            # 3. 调用OCR识别（默认混合策略）
            ocr_result = self.recognize(image, file_type=file_type, strategy="hybrid")
            
            # 4. 封装为标准化返回格式（适配OCRResult模型）
            if ocr_result["status"] == "success":
                return {
                    "status": "success",
                    "content": ocr_result["text"],
                    "confidence": ocr_result["confidence"],
                    "metadata": {
                        "engine": ocr_result["engine"],
                        "file_name": file.filename,
                        "content_type": file.content_type
                    }
                }
            else:
                return {
                    "status": "failure",
                    "error_message": ocr_result["error"],
                    "metadata": {
                        "engine": ocr_result["engine"],
                        "file_name": file.filename
                    }
                }
        except Exception as e:
            logger.error(f"处理上传文件失败：{str(e)}", exc_info=True)
            return {
                "status": "failure",
                "error_message": str(e),
                "metadata": {"file_name": file.filename}
            }

    def recognize(self, image: Image.Image, file_type: str = "image", strategy: str = "hybrid") -> dict:
        # 3种策略可选：hybrid(优先百度，失败降级TESS)、baidu(只用百度)、tesseract(只用TESS)
        if strategy == "baidu":
            return self._baidu_ocr(image)
        elif strategy == "tesseract":
            return self._tesseract_ocr(image, file_type)
        elif strategy == "hybrid":
            baidu_res = self._baidu_ocr(image)
            return baidu_res if baidu_res["status"] == "success" else self._tesseract_ocr(image, file_type)
        else:
            raise ValueError(f"不支持的OCR策略：{strategy}")

    def _baidu_ocr(self, image: Image.Image) -> dict:
        # 百度OCR需转二进制，内部封装，外部不用管
        try:
            img_byte = io.BytesIO()
            # 定义百度OCR支持的最大尺寸
            MAX_WIDTH = 4096
            MAX_HEIGHT = 4096

            # 获取原始图片尺寸
            width, height = image.size

            # 检查并调整图片尺寸
            if width > MAX_WIDTH or height > MAX_HEIGHT:
                # 计算缩放比例
                ratio = min(MAX_WIDTH / width, MAX_HEIGHT / height)
                # 计算新尺寸
                new_size = (int(width * ratio), int(height * ratio))
                # 调整图片大小
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                
            image.save(img_byte, format='PNG')
            res = self.baidu_client.basicGeneral(img_byte.getvalue())
            if res.get("error_code"):
                raise Exception(res["error_msg"])
            return {
                "status": "success", "engine": "baidu",
                "text": "\n".join([x["words"] for x in res.get("words_result", [])]),
                "confidence": 0.95
            }
        except Exception as e:
            logger.error(f"百度OCR失败：{str(e)}")
            return {"status": "failed", "engine": "baidu", "error": str(e)}

    def _tesseract_ocr(self, image: Image.Image, file_type: str) -> dict:
        # Tesseract配置复用config，和ocr_tasks逻辑一致
        try:
            cfg = self.tesseract_config.get(file_type, self.tesseract_config["image"])
            text = pytesseract.image_to_string(image, config=cfg, lang='chi_sim')
            return {
                "status": "success", "engine": "tesseract",
                "text": text, "confidence": 0.90
            }
        except Exception as e:
            logger.error(f"Tesseract OCR失败：{str(e)}")
            return {"status": "failed", "engine": "tesseract", "error": str(e)}

# 关键：创建实例，名称和review_router中导入的一致
ocr_strategy_service = OCRStrategyService()