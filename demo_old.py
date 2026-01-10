# -*- coding: utf-8 -*-
"""
电气图纸智能审查系统
功能：支持上传 CAD、PDF、图片格式图纸，自动提取文本并调用 AI 进行合规性审查
特点：多格式兼容、OCR 文本提取、AI 智能审查、结果可视化展示
维护人：[樊芮瑄]
日期：[2026-01-06]
"""

# ======================== 第一步：导入所有依赖库======================== 先把所有需要的工具库导入，相当于提前准备好所有要用的"工具"
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import requests
import streamlit as st
#from PIL import Image, ImageOps, ImageFilter
import tempfile
import io
import traceback
import base64
import numpy as np
import ezdxf  # 用于读取和处理 CAD 文件
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing import RenderContext, Frontend
import fitz  # PyMuPDF，用于 PDF 转图片和原生文本提取
from PIL import Image, ImageOps, ImageFilter
import subprocess
from dotenv import load_dotenv, find_dotenv  # 用于加载环境变量中的 API Key

def convert_dwg_to_dxf_from_path(dwg_file_path: str, output_dxf_path: str = None) -> str:
    """将 .dwg 文件转换为 .dxf 文件（基于 ODAFileConverter）。
    参数:
        dwg_file_path: .dwg 文件的绝对路径
        output_dxf_path: 输出的 .dxf 文件路径，如果未提供则自动生成
    返回:
        转换后的 .dxf 文件的绝对路径
    异常:
        如果转换失败或路径不存在，抛出 Exception
    """
    if not os.path.exists(dwg_file_path):
        raise FileNotFoundError(f"未找到 DWG 文件: {dwg_file_path}")

    # 根据实际安装路径修改转换器路径
    converter_path = r"D:\Program Files\ODA\ODAFileConverter 26.10.0\ODAFileConverter.exe"
    if not os.path.exists(converter_path):
        raise FileNotFoundError(f"ODA 转换器未找到，请检查路径: {converter_path}")

    input_folder = os.path.dirname(dwg_file_path)
    output_folder = os.path.join(input_folder, "converted_dxf")
    os.makedirs(output_folder, exist_ok=True)
    dxf_path = os.path.join(output_folder, os.path.basename(dwg_file_path).replace('.dwg', '.dxf'))

    # 构建命令（根据 ODAFileConverter 的命令行参数）
    cmd = f'"{converter_path}" "{input_folder}" "{output_folder}" "ACAD2018" "DXF" 0 1'

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0 and os.path.exists(dxf_path):
        return dxf_path
    else:
        error_msg = f"DWG 转换失败: {result.stderr}"
        print(f"执行的命令是: {cmd}")
        raise Exception(error_msg)

def cad_to_png(cad_file_path: str, output_png_path: str = "temp_cad_render.png") -> str:
    """
    将 CAD 文件（.dwg/.dxf）转换为 PNG 图像
    :param cad_file_path: 输入 CAD 文件路径
    :param output_png_path: 输出 PNG 图像路径
    :return: 输出 PNG 图像的路径
    """

    #新增：检查并转换 .dwg 文件
    file_ext = os.path.splitext(cad_file_path)[1].lower()
    if file_ext == '.dwg':
        #调用转换函数
        #注意：这里需要修改 convert_dwg_to_dxf 函数，让它接收文件路径而不是文件对象
        dxf_file_path = convert_dwg_to_dxf_from_path(cad_file_path)
        #将路径替换为转换后的 .dxf 文件
        cad_file_path = dxf_file_path

    # 1. 读取 CAD 文件（自动识别 .dwg/.dxf）
    doc = ezdxf.readfile(cad_file_path)
    msp = doc.modelspace()  # 获取模型空间（CAD 图纸的核心内容）

    # 2. 初始化 matplotlib 渲染器
    fig, ax = plt.subplots(figsize=(10, 10))  # 设置图像大小，可根据需要调整
    ctx = RenderContext(doc)
    out = MatplotlibBackend(ax)
    frontend = Frontend(ctx, out)

    # 3. 渲染模型空间内容到图像
    frontend.draw_layout(msp, finalize=True)

    # 4. 保存图像（关闭坐标轴，让图像更干净）
    ax.axis('off')
    plt.savefig(output_png_path, dpi=30, bbox_inches='tight', pad_inches=0)
    plt.close(fig)

    return output_png_path

# 测试用例（可选，运行前请替换为你的 CAD 文件路径）
if __name__ == "__main__":
    test_cad_path = "c:\\Users\\HP\\Desktop\\新建文件夹\\CAD_Projects\\改动CAD图\\电气主接线及电气总平面布置图20251009161743（错）.dwg"  # 替换为你的 CAD 文件路径
    if os.path.exists(test_cad_path):
        png_path = cad_to_png(test_cad_path)
        print(f"CAD 转换完成，图像保存至：{png_path}")
    else:
        print("测试 CAD 文件不存在！")

# 优先从项目根目录或查找到的 .env 文件加载变量，保证后续 os.getenv 能读取到
dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path)
else:
    load_dotenv()

# 兼容多种命名：如果只配置了 ERNIE_API_KEY，将其复制到 AI_API_KEY，启用原有逻辑
if not os.getenv("AI_API_KEY") and os.getenv("ERNIE_API_KEY"):
    os.environ["AI_API_KEY"] = os.getenv("ERNIE_API_KEY")

#####

# ======================== 第二步：全局配置（导入库后立即配置，全局生效） ========================
#全局配置只运行一次，用于设置工具的核心参数，避免重复代码

# 1. 配置 baidu OCR 引擎路径
OCR_API_KEY = os.getenv("OCR_API_KEY")
OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY")

# 2. 配置 Streamlit 页面基础信息（界面展示用）
st.set_page_config(page_title="电气设计图纸审查AI小助手", layout="wide")

# 3. 加载环境变量（用于读取 AI 模型的 API Key，避免硬编码）
#load_dotenv()  # 从项目根目录的 .env 文件中加载变量
#API_KEY = os.getenv("AI_API_KEY")  # 请确保 .env 文件中有 AI_API_KEY 这个变量


# ======================== 第三步：定义工具函数（封装重复逻辑，主逻辑中直接调用） ========================
# 【给自己的解释】：工具函数是"功能模块"，每个函数负责一个具体任务，方便调试和修改
# 【Copilot 协作点】：这些工具函数可以直接让 Copilot 生成或优化，只需描述功能需求
def get_baidu_access_token():
    """获取百度 API 的 access_token"""
    OCR_API_KEY = os.getenv("OCR_API_KEY")
    OCR_SECRET_KEY = os.getenv("OCR_SECRET_KEY")
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


    # ======================== 核心：调用百度文心一言（ERNIE Bot） ========================
    # 说明：此处实现获取 access_token（需 ERNIE_API_KEY 和 ERNIE_SECRET_KEY），
    #       并调用 chat/completions 接口。返回结果解析具备容错能力。

def call_ernie_api(prompt):
    api_key = os.getenv("ERNIE_API_KEY")
    if not api_key:
        return "【配置错误】请在 .env 文件中设置 ERNIE_API_KEY"

    api_url = "https://qianfan.baidubce.com/v2/chat/completions"

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


# ======================== 第四步：主逻辑（页面交互 + 功能调用，程序入口） ========================
# 主逻辑是页面的交互流程，用户操作触发工具函数的调用，是程序的核心执行入口

# 构造一个类似 Streamlit 上传文件的对象，供 extract_text_from_file 使用
class _TempUploaded:
    def __init__(self, path):
        self.name = os.path.basename(path)
        with open(path, 'rb') as f:
            self._data = f.read()

    def getbuffer(self):
        return self._data

def main():
    # 页面标题和说明
    st.title("📄 电气设计图纸审查AI小助手")
    st.markdown("---")
    st.subheader("使用说明")
    st.markdown("1. 支持上传格式：PDF、PNG、JPG、JPEG、WEBP、DWG、DXF")
    st.markdown("2. CAD 图纸(.dwg,.dxf)可上传，系统会自动转换为图片进行处理")
    st.markdown("3. 系统将自动提取文本并进行 AI 合规性审查")
    st.markdown("---")

    # 1. 读取公司审查规则文件
    # 审查规则单独放在文件中，方便修改和维护，无需改动代码
    rules_file_path = "company_rules.txt"
    if not os.path.exists(rules_file_path):
        st.error(f"未找到审查规则文件：{rules_file_path}")
        st.info("请在项目根目录创建 company_rules.txt 文件，并写入审查规则")
        return
    with open(rules_file_path, "r", encoding="utf-8") as f:
        company_review_rules = f.read()

    # 2. 文件上传组件（核心交互入口）
    uploaded_file = st.file_uploader(
        label="请上传电气图纸",
        type=["pdf", "png", "jpg", "jpeg", "webp","dwg","dxf"],
        help="支持原生 PDF、扫描 PDF、图片格式（含 WEBP），CAD 请先导出为 PDF/图片"
    )

    # 3. 当用户上传文件后，执行核心业务逻辑
    if uploaded_file is not None:
        st.success(f"已上传文件：{uploaded_file.name}")
        st.markdown("---")

        # 判断文件类型并处理 CAD

        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext in ['.dwg', '.dxf']:
            # 保存上传的 CAD 文件到临时路径
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_cad:
                tmp_cad.write(uploaded_file.getbuffer())
                temp_cad_path = tmp_cad.name
            try:
            # 调用 CAD 转换函数，得到 PNG 路径
                png_path = cad_to_png(temp_cad_path)
            # 用转换后的 PNG 文件替换 uploaded_file 以便后续复用逻辑
                uploaded_file = _TempUploaded(png_path)
            except Exception as e:
                st.error(f"CAD 转换失败: {e}")
            finally:
                try:
                    if os.path.exists(temp_cad_path):
                        os.remove(temp_cad_path)
                except Exception:
                    pass
        else:
            # 其他格式直接使用 uploaded_file 处理
            pass

        # 步骤一：提取图纸文本
        st.subheader("第一步：图纸文本提取结果")
        with st.spinner("正在提取文本...（扫描件可能需要稍长时间）"):
            extracted_text = extract_text_from_file(uploaded_file)
        # 展示提取的文本
        st.text_area(
            label="提取的文本内容",
            value=extracted_text,
            height=300,
            placeholder="文本提取完成后将显示在此处..."
        )

        st.markdown("---")

        # 步骤二：AI 智能审查
        st.subheader("第二步：AI 智能审查结果")
        with st.spinner("AI 正在审查图纸...请稍候"):
            review_result = call_ai_review(extracted_text, drawing_name = uploaded_file.name)
        # 展示审查结果
        import json
        import pandas as pd

        try:
            review_result_dict = json.loads(review_result)
        except json.JSONDecodeError:
            st.success(review_result)
        else:
            if "提取结果" in review_result_dict and "核心字段" in review_result_dict["提取结果"]:
                st.subheader("提取结果")
                df = pd.DataFrame(review_result_dict["提取结果"]["核心字段"])
                st.dataframe(df, use_container_width=True)

            if "问题识别" in review_result_dict:
                st.subheader("问题识别")
            for category, issues in review_result_dict["问题识别"].items():
                if issues:
                    clean_items = [str(it).strip().strip('"').strip("'") for it in issues if str(it).strip()]
                if clean_items:
                    st.error(f"{category}:")
                    for idx, item in enumerate(clean_items, 1):
                        st.write(f"{idx}. {item}")
            if "改进建议" in review_result_dict:
                st.subheader("改进建议")
            for category, suggestions in review_result_dict["改进建议"].items():
                if suggestions:
                    st.success(f"{category}: {', '.join(suggestions)}")

# ======================== 程序入口（固定写法，确保主逻辑只在直接运行时执行） ========================
if __name__ == "__main__":
    main()