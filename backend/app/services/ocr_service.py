import os
import requests
import base64
import tempfile
import traceback
from PIL import Image, ImageOps, ImageFilter
ImageFilter
import fitz  # PyMuPDF
from app.core.config import settings
from app.tasks.ocr_tasks import perform_ocr


def perform_ocr_service (file_content: bytes, file_type: str) -> dict:
    """封装 OCR 的业务逻辑"""
    try:
        # 根据文件类型进行不同的预处理
        if file_type in ["dxf", "dwg"]:
            # 先调用 CAD 服务将图纸渲染为图片
            from app.services.cad_service import render_cad_to_image
            image_content = render_cad_to_image(file_content, file_type)
            # 再对渲染后的图片进行OCR
            ocr_result = perform_ocr.delay(image_content, file_type="image").get()
        else:
            # PDF 和图片直接调用 OCR 任务
            ocr_result = perform_ocr.delay(file_content, file_type=file_type).get()
            # 处理OCR结果
            if ocr_result ["status"] != "success":
                return{
                    "status": "failed",
                    "message": "OCR 识别失败",
                    "error": ocr_result.get("error")
                }
        return ocr_result
    except Exception as e:
        return {
            "status": "failed",
            "error": str (e),
            "message": "OCR 服务调用失败"
        }


def get_baidu_access_token():
    """获取百度 API 的 access_token"""
    OCR_API_KEY = settings.OCR_API_KEY
    OCR_SECRET_KEY = settings.OCR_SECRET_KEY
    if not OCR_API_KEY or not OCR_SECRET_KEY:
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
        return token_response.json().get("access_token")
    except Exception:
        return None

def baidu_ocr(image_path):
    """调用百度高精度 OCR 识别图片"""
    # 先获取 access_token
    access_token = get_baidu_access_token()
    if not access_token:
        return "获取百度 OCR 授权失败，请检查 API Key 和网络连接。"
    # 读取并编码图片
    with open(image_path, 'rb') as f:
        img_base64 = base64.b64encode(f.read()).decode('utf-8')
    # 调用高精度 OCR 接口
    ocr_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/accurate?access_token={access_token}"
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    try:
        ocr_response = requests.post(ocr_url, data={"image": img_base64}, headers=headers, timeout=30)
        ocr_response.raise_for_status()
    except Exception as e:
        return f"OCR 识别请求失败: {e}"
    # 解析识别结果
    try:
        result = ocr_response.json()
        if "words_result" in result:
            return "\n".join([item.get("words", "") for item in result["words_result"]])
        else:
            return f"OCR 结果解析失败: {result}"
    except Exception as e:
        return f"OCR 结果解析失败: {e}"

def _preprocess_image(img: Image.Image) -> Image.Image:
        try:
            img = img.convert("L")  # 灰度
            img = ImageOps.autocontrast(img)  # 拉伸对比度
            img = img.filter(ImageFilter.MedianFilter(size=3))  # 去噪
            # 简单二值化（阈值可调整或改为自适应）
            threshold = 128
            img = img.point(lambda p: 255 if p > threshold else 0).convert("L")
            return img
        except Exception:
            return img

def extract_text_from_file(uploaded_file):
    """
    统一处理不同格式的上传文件，提取文本内容（增强版）
    特性：
    - 支持更多图片格式（如 webp、bmp、tiff）
    - 对图像做简单预处理（灰度化、去噪、自动对比、二值化）以提高 OCR 精度
    - 更完善的错误处理与日志，确保临时文件在任何情况下都被清理
    参数：
        uploaded_file: Streamlit 上传的文件对象
    返回：
        extracted_text: 提取的文本内容字符串，出现错误时返回带错误信息的字符串
    """
    
    file_ext = uploaded_file.name.split('.')[-1].lower()
    supported_image_exts = {"png", "jpg", "jpeg", "webp", "bmp", "tiff","dwg","dxf"}
    extracted_text = ""
    tmp_path = None

    try:
        # 使用安全的临时文件，确保在 finally 中删除
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name

        if file_ext == "pdf":
            try:
                doc = fitz.open(tmp_path)
            except Exception as e:
                raise RuntimeError(f"无法打开 PDF 文件: {e}")

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                page_text = page.get_text().strip()
                # 如果原生文本极短，则认为是扫描件，使用 OCR
                if len(page_text) < 10:
                    try:
                        mat = fitz.Matrix(2, 2)  # 放大渲染以提高 OCR 准确度
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        proc = _preprocess_image(img)                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_tmp:
                            proc.save(img_tmp, format="PNG")
                            img_tmp_path = img_tmp.name  # 保存预处理后的图片到临时文件
                        page_text = baidu_ocr(img_tmp_path)  # 调用百度 OCR
                        os.unlink(img_tmp_path)  # 删除临时图片
                    except Exception as e:
                        page_text = f"[OCR 提取失败：{e}]"
                extracted_text += f"=== 第 {page_num + 1} 页 ===\n{page_text}\n\n"
            doc.close()

        elif file_ext in supported_image_exts:
            try:
                image = Image.open(tmp_path)
            except Exception as e:
                raise RuntimeError(f"无法打开图像文件: {e}")
            proc = _preprocess_image(image)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_tmp:
                proc.save(img_tmp, format="PNG")
                img_tmp_path = img_tmp.name  # 保存预处理后的图片到临时文件
            extracted_text = baidu_ocr(img_tmp_path)  # 调用百度 OCR
            os.unlink(img_tmp_path)  # 删除临时图片
        else:
            raise ValueError(f"不支持的文件格式：{file_ext}")

    except Exception as e:
        tb = traceback.format_exc()
        extracted_text = f"[提取失败] 错误：{e}\n详细信息：\n{tb}"

    finally:
        # 尝试删除临时文件（即使发生错误也要清理）
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    return extracted_text