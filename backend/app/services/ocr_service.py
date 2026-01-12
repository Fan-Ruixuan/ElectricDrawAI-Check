import os
import requests
import base64
import tempfile
import traceback
import hashlib
import cv2
import numpy as np
from io import BytesIO
from PIL import Image, ImageOps, ImageFilter
import fitz  # PyMuPDF
import logging

# 项目配置和依赖导入
from app.core.config import settings
from app.tasks.ocr_tasks import perform_ocr

# ========== 日志配置 ==========
logger = logging.getLogger(__name__)

# ========== 百度OCR授权函数 ==========
def get_baidu_access_token():
    """获取百度 API 的 access_token"""
    OCR_API_KEY = settings.OCR_API_KEY
    OCR_SECRET_KEY = settings.OCR_SECRET_KEY
    if not OCR_API_KEY or not OCR_SECRET_KEY:
        logger.error("百度OCR的API_KEY或SECRET_KEY未配置")
        return None
    token_url = "https://aip.baidubce.com/oauth/2.0/token"
    token_params = {
        "grant_type": "client_credentials",
        "client_id": OCR_API_KEY,
        "client_secret": OCR_SECRET_KEY
    }
    try:
        token_response = requests.post(token_url, params=token_params, timeout=10)
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        logger.info(f"百度OCR Access Token: {access_token}")
        return access_token
    except Exception as e:
        logger.error(f"获取百度access_token失败：{str(e)}", exc_info=True)
        return None

# ========== 图片预处理函数 ==========
def _preprocess_image(img: Image.Image) -> Image.Image:
    """优化版图片预处理（增加尺寸限制）"""
    try:
        # 1. 灰度化
        img = img.convert("L")
        
        # 2. 放大图片
        width, height = img.size
        img = img.resize((width*2, height*2), Image.Resampling.LANCZOS)
        
        # 新增：限制图片最大尺寸（百度OCR限制≤4096×4096）
        max_size = 4096
        if img.width > max_size or img.height > max_size:
            # 按比例缩放至最大尺寸内
            scale = min(max_size / img.width, max_size / img.height)
            new_width = int(img.width * scale)
            new_height = int(img.height * scale)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"图片尺寸超限，缩放到：{new_width}x{new_height}")
        
        # 3. 增强对比度
        img = ImageOps.autocontrast(img, cutoff=2)
        
        # 4. 去噪
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        # 5. 自适应二值化
        img_np = np.array(img)
        img_np = cv2.adaptiveThreshold(
            img_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        img = Image.fromarray(img_np).convert("L")
        
        logger.debug("图片预处理成功，尺寸：%sx%s", img.size[0], img.size[1])
        return img
    except Exception as e:
        logger.error(f"图片预处理失败：{str(e)}", exc_info=True)
        return img

# ========== 百度OCR核心函数（兼容路径/字节两种调用） ==========
def baidu_ocr(image_path=None, image_bytes=None):
    """
    调用百度高精度OCR
    :param image_path: 图片路径（二选一）
    :param image_bytes: 图片字节（二选一）
    """
    # 1. 获取access_token
    access_token = get_baidu_access_token()
    if not access_token:
        return "获取百度 OCR 授权失败，请检查 API Key 和网络连接。"
    
    # 2. 处理图片（路径/字节二选一）
    try:
        if image_path:
            with Image.open(image_path) as img:
                processed_img = _preprocess_image(img)
                img_byte_arr = BytesIO()
                processed_img.save(img_byte_arr, format='PNG', dpi=(300, 300))
                img_bytes = img_byte_arr.getvalue()
        elif image_bytes:
            img = Image.open(BytesIO(image_bytes))
            processed_img = _preprocess_image(img)
            img_byte_arr = BytesIO()
            processed_img.save(img_byte_arr, format='PNG', dpi=(300, 300))
            img_bytes = img_byte_arr.getvalue()
        else:
            return "未提供图片路径或字节数据"
    except Exception as e:
        error_msg = f"图片加载/预处理失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
    
    # 3. 调用百度OCR接口
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    ocr_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate?access_token={access_token}"
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    data = {
        "image": img_base64,
        "detect_direction": "true",
        "image_quality_enhance": "true",
        "language_type": "CHN_ENG"
    }
    
    try:
        ocr_response = requests.post(ocr_url, data=data, headers=headers, timeout=30)
        ocr_response.raise_for_status()
    except Exception as e:
        error_msg = f"OCR 识别请求失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
    
    # 4. 解析结果
    try:
        result = ocr_response.json()
        if "error_code" in result:
            error_msg = f"百度OCR接口错误: {result['error_msg']}（错误码：{result['error_code']}）"
            logger.error(error_msg)
            return error_msg
        if "words_result" in result and result["words_result"]:
            ocr_text = "\n".join([item.get("words", "").strip() for item in result["words_result"]])
            logger.info(f"OCR识别成功，提取文本长度：{len(ocr_text)}")
            return ocr_text
        else:
            logger.warning(f"OCR 结果为空: {str(result)}")
            return ""
    except Exception as e:
        error_msg = f"OCR 结果解析失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg

# ========== OCR服务封装函数 ==========
def perform_ocr_service(img_bytes: bytes, file_type: str) -> dict:
    """OCR识别服务（纯字节流，无临时文件）"""
    try:
        # 直接调用baidu_ocr（传字节）
        ocr_result = baidu_ocr(image_bytes=img_bytes)
        
        # 校验结果
        if not ocr_result:
            logger.warning(f"OCR识别结果为空（文件类型：{file_type}）")
            return {
                "status": "success",
                "structured_data": {"text": "", "file_type": file_type, "page_count": 1}
            }
        if "失败" in ocr_result or "错误" in ocr_result:
            logger.error(f"OCR识别失败，结果：{ocr_result}")
            return {
                "status": "failed",
                "error": ocr_result,
                "message": f"OCR识别失败：{ocr_result}"
            }
        
        # 返回结果
        return {
            "status": "success",
            "structured_data": {
                "text": ocr_result,
                "file_type": file_type,
                "page_count": 1
            }
        }
    
    except Exception as e:
        error_msg = f"perform_ocr_service异常：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error": error_msg,
            "message": error_msg
        }

# ========== 文件文本提取函数（最终版） ==========
def extract_text_from_file(uploaded_file):
    """统一处理不同格式的上传文件，提取文本内容"""
    file_ext = uploaded_file.name.split('.')[-1].lower()
    # 初始化临时目录
    os.makedirs(settings.OCR_TEMP_DIR, exist_ok=True)
    logger.info(f"OCR临时目录：{settings.OCR_TEMP_DIR}")
    logger.info(f"临时目录是否存在：{os.path.exists(settings.OCR_TEMP_DIR)}")
    
    supported_image_exts = {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}
    supported_cad_exts = {"dwg", "dxf"}
    extracted_text = ""
    tmp_path = None
    temp_files_to_clean = []

    try:
        # 1. 保存上传文件到临时路径
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name
            temp_files_to_clean.append(tmp_path)

        # 2. 处理PDF文件（核心修复：直接传字节，跳过本地临时文件）
        if file_ext == "pdf":
            from pdf2image import convert_from_bytes
            # 读取PDF字节
            with open(tmp_path, "rb") as f:
                pdf_bytes = f.read()
            logger.info(f"Poppler路径：{settings.POPPLER_PATH}")
            logger.info(f"PDF文件大小：{len(pdf_bytes)} 字节")
            
            # PDF转图片
            images = convert_from_bytes(
                pdf_bytes,
                dpi=300,
                poppler_path=settings.POPPLER_PATH
            )
            logger.info(f"PDF转图片成功，共{len(images)}页")
            
            # 逐页OCR（直接传图片字节）
            for page_num, img in enumerate(images):
                # 图片转字节
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format='PNG', dpi=(300, 300))
                img_bytes = img_byte_arr.getvalue()
                # 调用OCR（传字节，不保存本地）
                page_text = baidu_ocr(image_bytes=img_bytes)
                # 拼接结果
                extracted_text += f"=== 第 {page_num + 1} 页 ===\n{page_text}\n\n"

        # 3. 处理普通图片文件
        elif file_ext in supported_image_exts:
            img = Image.open(tmp_path)
            proc = _preprocess_image(img)
            # 保存预处理后的图片
            img_tmp_path = os.path.join(
                settings.OCR_TEMP_DIR, 
                f"img_{hashlib.md5(proc.tobytes()).hexdigest()[:8]}.png"
            )
            proc.save(img_tmp_path, format="PNG")
            temp_files_to_clean.append(img_tmp_path)
            # 调用OCR
            extracted_text = baidu_ocr(image_path=img_tmp_path)

        # 4. 处理CAD文件
        elif file_ext in supported_cad_exts:
            from app.services.cad_service import render_cad_to_image
            # 读取CAD文件
            with open(tmp_path, "rb") as f:
                file_content = f.read()
            # CAD转图片字节
            img_bytes = render_cad_to_image(file_content, file_ext)
            # 重置字节流指针
            img_stream = BytesIO(img_bytes)
            img_stream.seek(0)
            img = Image.open(img_stream)
            # 预处理
            proc = _preprocess_image(img)
            img_tmp_path = os.path.join(
                settings.OCR_TEMP_DIR, 
                f"cad_{hashlib.md5(proc.tobytes()).hexdigest()[:8]}.png"
            )
            proc.save(img_tmp_path, format="PNG")
            temp_files_to_clean.append(img_tmp_path)
            # 调用OCR
            extracted_text = baidu_ocr(image_path=img_tmp_path)

        # 5. 不支持的格式
        else:
            raise ValueError(f"不支持的文件格式：{file_ext}")

    except Exception as e:
        tb = traceback.format_exc()
        extracted_text = f"[提取失败] 错误：{e}\n详细信息：\n{tb}"
        logger.error(f"文件文本提取失败（格式：{file_ext}）：{str(e)}", exc_info=True)

    finally:
        # 统一清理临时文件
        for file_path in temp_files_to_clean:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"清理临时文件：{file_path}")
                except Exception as e:
                    logger.warning(f"清理临时文件失败：{file_path}，错误：{str(e)}")

    return extracted_text