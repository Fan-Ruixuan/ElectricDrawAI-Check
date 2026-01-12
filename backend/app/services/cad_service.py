import sys
import os
import io
import logging
import hashlib
logging.getLogger('ezdxf').setLevel(logging.WARNING)
import time
from pathlib import Path
from typing import Optional, Dict
import subprocess
import ezdxf


import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from pdf2image import convert_from_bytes
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

from PIL import Image, ImageOps, ImageFilter
import numpy as np
import cv2

file_process_cache: Dict[str, dict] = {}
CACHE_EXPIRE_SECONDS = 300


# ========== 补充缺失的核心导入 ==========
from app.core.config import settings

# 初始化logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 修复：导入AIService类并实例化（实例名和方法名区分）
from app.services.ai_service import AIService
ai_service_instance = AIService() 

# 定义自定义异常类
class CADConversionError(Exception):
    """CAD文件转换过程中发生的错误"""
    pass

class CADRenderError(Exception):
    """CAD文件渲染为PNG过程中发生的错误"""
    pass

# ========== 补充缺失的核心依赖函数 ==========
def _get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent  # 根据实际目录结构调整

def save_temp_file(file_content: bytes, filename: str) -> str:
    """保存二进制内容为临时文件，返回文件路径（同一文件只存一次）"""
    file_hash = hashlib.md5(file_content).hexdigest()[:8] 
    temp_dir = _get_project_root() / "temp" / "cad"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{file_hash}_{filename}"  # 哈希+文件名，确保唯一
    
    if temp_path.exists():
        logger.info(f"文件已存在，复用临时文件：{temp_path}")
        return str(temp_path)
    
    with open(temp_path, "wb") as f:
        f.write(file_content)
    logger.info(f"临时文件已保存：{temp_path}")
    return str(temp_path)

# ========== 缓存处理函数 ==========
def _get_file_hash(file_content: bytes) -> str:
    """生成文件内容的唯一哈希（MD5保证稳定性）"""
    return hashlib.md5(file_content).hexdigest()

def clean_temp_cad_files(keep_latest: int = 10):
    """清理临时CAD文件，保留最新10个（避免频繁创建）"""
    temp_dir = _get_project_root() / "temp" / "cad"
    if not temp_dir.exists():
        return
    
    files = sorted(
        temp_dir.glob("*"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    
    for file in files[keep_latest:]:
        try:
            file.unlink()
            logger.info(f"清理临时文件：{file}")
        except Exception as e:
            logger.warning(f"清理临时文件失败：{file}，错误：{str(e)}")

def _check_cache(file_hash: str) -> Optional[dict]:
    """检查缓存，返回有效结果或None"""
    if file_hash not in file_process_cache:
        return None
    
    cache_data = file_process_cache[file_hash]
    if time.time() - cache_data["timestamp"] > CACHE_EXPIRE_SECONDS:
        del file_process_cache[file_hash]
        return None
    
    return cache_data

def _update_cache(file_hash: str, status: str, result: dict = None):
    """更新缓存"""
    file_process_cache[file_hash] = {
        "status": status,
        "result": result,
        "timestamp": time.time()
    }

# ========== 业务函数 ==========
def process_image_service(file_content: bytes, filename: str) -> dict:
    """处理图片文件的业务逻辑"""
    # 延迟导入，解决循环依赖
    from app.services.ocr_service import perform_ocr_service
    from app.services.common_service import generate_report_service
    
    try:
        # 调用 OCR 服务
        ocr_result = perform_ocr_service(file_content, "image")
        if ocr_result["status"] != "success":
            return ocr_result
        
        # 修复1：调用实例的ai_review_service方法
        ai_result = ai_service_instance.ai_review_service(ocr_result["structured_data"], filename)
        if ai_result["status"] != "success":
            return ai_result
        
        # 调用报告生成服务
        report = generate_report_service(ai_result, filename)
        return {
            "status": "success",
            "result": {
                "ocr": ocr_result,
                "ai_review": ai_result,
                "report": report
            },
            "message": "图片文件处理完成"    
        }
    except Exception as e:
        logger.error(f"图片文件处理失败：{str(e)}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "message": "图片文件处理失败"
        }

def _validate_dwg_exists(dwg_file_path: str) -> Path:
    """验证DWG文件存在，返回Path对象"""
    dwg_path = Path(dwg_file_path)
    if not dwg_path.exists():
        logger.error("DWG file not found: %s", dwg_file_path)
        raise FileNotFoundError(f"DWG file not found: {dwg_file_path}")
    return dwg_path

def _get_and_validate_converter_path() -> Path:
    """获取并验证ODA转换器路径"""
    converter_path_str = settings.ODA_CONVERTER_PATH
    converter_path = Path(converter_path_str)
    if not converter_path.exists():
        logger.error("ODA converter not found at %s", converter_path)
        raise FileNotFoundError(f"ODA converter not found: {converter_path}")
    return converter_path

def _determine_output_dxf_path(dwg_path: Path, output_dxf_path: Optional[str]) -> Path:
    """确定DXF输出路径"""
    if output_dxf_path:
        out_path = Path(output_dxf_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        project_root = _get_project_root()
        out_folder = project_root / "temp" / "output"
        out_folder.mkdir(parents=True, exist_ok=True)
        dxf_filename = dwg_path.stem + ".dxf"
        out_path = out_folder / dxf_filename
    return out_path

def _build_oda_converter_command(converter_path: Path, input_file: str, output_folder: str) -> list:
    """严格对齐ODA官方命令格式"""
    input_folder = str(Path(input_file).parent)
    file_filter = Path(input_file).name

    quoted_converter = f'"{str(converter_path)}"'
    quoted_input_folder = f'"{input_folder}"'
    quoted_output_folder = f'"{output_folder}"'
    quoted_filter = f'"{file_filter}"'

    return [
        quoted_converter,
        quoted_input_folder,
        quoted_output_folder,
        settings.ODA_TARGET_VERSION,
        "DXF",
        settings.ODA_OTHER_PARAM_1,  # 填0
        settings.ODA_OTHER_PARAM_2,  # 填1
        quoted_filter
    ]

def extract_layers_from_dxf(dxf_file_path: str, target_layers: list = None) -> dict:
    """从 DXF 文件中提取指定图层的所有实体"""
    if target_layers is None:
        target_layers = []

    dxf_path = Path(dxf_file_path)
    if not dxf_path.exists():
        logger.error("DXF 文件未找到: %s", dxf_path)
        raise FileNotFoundError(f"DXF 文件未找到: {dxf_path}")

    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()
    except Exception as e:
        logger.error(f"读取DXF文件错误详情: {str(e)}", exc_info=True)
        raise CADConversionError(f"读取 DXF 文件失败: {dxf_path}") from e

    extracted_data = {}
    for entity in msp:
        try:
            entity_layer = entity.dxf.layer
        except Exception:
            continue

        if target_layers and entity_layer not in target_layers:
            continue

        extracted_data.setdefault(entity_layer, [])

        entity_info = {
            "type": entity.dxftype(),
            "handle": getattr(entity.dxf, "handle", None),
            "layer": entity_layer,
        }

        etype = entity.dxftype()
        if etype == "TEXT":
            try:
                insert = getattr(entity.dxf, "insert", None)
                insert_tuple = (insert.x, insert.y) if insert is not None else None
                entity_info.update({"text": getattr(entity.dxf, "text", None), "insert": insert_tuple})
            except Exception:
                pass
        elif etype == "LINE":
            try:
                start = getattr(entity.dxf, "start", None)
                end = getattr(entity.dxf, "end", None)
                if start is not None and end is not None:
                    entity_info.update({"start": (start.x, start.y), "end": (end.x, end.y)})
            except Exception:
                pass

        extracted_data[entity_layer].append(entity_info)

    logger.info(
        "成功提取 DXF 图层",
        extra={"dxf_file_path": str(dxf_path), "extracted_layers": list(extracted_data.keys())},
    )
    return extracted_data

def convert_dwg_to_dxf_from_path(dwg_file_path: str, output_dxf_path: Optional[str] = None) -> str:
    """将DWG文件转换为DXF（通过ODA转换器，增加重试和兼容）"""
    dwg_path = _validate_dwg_exists(dwg_file_path)
    converter_path = _get_and_validate_converter_path()
    out_path = _determine_output_dxf_path(dwg_path, output_dxf_path)

    # 重试机制：最多重试1次
    max_retries = 1
    retry_count = 0
    while retry_count < max_retries:
        input_file = str(dwg_path)
        output_folder = str(out_path.parent)
        cmd = _build_oda_converter_command(converter_path, input_file, output_folder)

        logger.debug("Executing ODAFileConverter (重试%d): %s", retry_count, " ".join(cmd))

        try:
            cmd_str = " ".join(cmd)
            result = subprocess.run(
                cmd_str, 
                capture_output=True, 
                text=True, 
                timeout=120,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except subprocess.TimeoutExpired as e:
            logger.error(f"ODAFileConverter 超时错误详情: {str(e)}", exc_info=True)
            retry_count += 1
            continue
        except Exception as e:
            logger.error(f"执行ODAFileConverter错误详情: {str(e)}", exc_info=True)
            retry_count += 1
            continue

        if result.returncode == 0 and out_path.exists():
            try:
                ezdxf.readfile(str(out_path))
            except Exception as e:
                logger.error(f"生成的DXF文件无效：{str(e)}", exc_info=True)
                retry_count += 1
                continue
            
            logger.info(
                "DWG转换为DXF成功",
                extra={
                    "input_file": str(dwg_path),
                    "output_file": str(out_path)
                }
            )
            return str(out_path.resolve())
        else:
            logger.error(
                "DWG conversion failed (code=%s). stdout: %s stderr: %s",
                result.returncode,
                result.stdout,
                result.stderr,
            )
            retry_count += 1
    
    # 所有重试失败
    raise CADConversionError(f"DWG转换失败（已重试{max_retries}次）：{result.stderr or result.stdout}")

def convert_dwg_to_dxf_from_bytes(file_content: bytes, filename: str) -> dict:
    """将二进制的 DWG 文件内容转换为 DXF"""
    temp_file_path = save_temp_file(file_content, filename)
    
    if not Path(temp_file_path).exists():
        raise FileNotFoundError(f"临时文件{temp_file_path}未成功创建")
    
    dxf_file_path = convert_dwg_to_dxf_from_path(str(temp_file_path))
    
    return {
        "status": "success",
        "dxf_file": dxf_file_path, 
        "original_filename": filename,
        "dxf_file_path": dxf_file_path
    }

def cad_to_png(cad_file_path: str, output_png_path: str = "temp_cad_render.png") -> str:
    """将CAD文件（DWG/DXF）转换为PNG图片"""
    from ezdxf import DXFError

    cad_path = Path(cad_file_path)
    if not cad_path.exists():
        logger.error("CAD file not found: %s", cad_file_path)
        raise FileNotFoundError(f"CAD file not found: {cad_file_path}")

    try:
        if cad_path.suffix.lower() == ".dwg":
            logger.info("Input is DWG; converting to DXF first: %s", cad_file_path)
            dxf_path = convert_dwg_to_dxf_from_path(str(cad_path))
            cad_path = Path(dxf_path)

        doc = ezdxf.readfile(str(cad_path))
    except FileNotFoundError:
        raise
    except DXFError as e:
        logger.error(f"无效的DXF/CAD文件错误详情: {str(e)}", exc_info=True)
        raise CADRenderError(f"Invalid DXF/CAD file: {cad_path}") from e
    except Exception as e:
        logger.error(f"读取CAD文件错误详情: {str(e)}", exc_info=True)
        raise CADRenderError(f"Failed to read CAD file: {cad_path}") from e

    try:
        msp = doc.modelspace()
        fig, ax = plt.subplots(figsize=settings.CAD_RENDER_FIGSIZE)
        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        frontend = Frontend(ctx, out)
        frontend.draw_layout(msp, finalize=True)
        ax.axis("off")

        out_path = Path(output_png_path)
        if not out_path.is_absolute():
            out_path = _get_project_root() / out_path
            out_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(
            str(out_path),
            dpi=300,
            bbox_inches="tight",
            pad_inches=0
        )
        plt.close(fig)
        logger.info("CAD rendered to PNG: %s", out_path)
        return str(out_path.resolve())

    except Exception as e:
        logger.error(f"渲染错误详情: {str(e)}", exc_info=True)
        raise CADRenderError("Failed to render CAD to PNG") from e

def render_cad_to_image(file_content: bytes, file_type: str) -> bytes:
    """将DWG/DXF二进制内容渲染为图片二进制（适配OCR服务入参）"""
    file_hash = hashlib.md5(file_content).hexdigest()
    
    # 1. 检查缓存
    cache_data = _check_cache(file_hash)
    if cache_data:
        if cache_data["status"] == "success":
            logger.info(f"复用缓存结果：{file_hash}")
            return cache_data["result"]
        elif cache_data["status"] == "processing":
            raise CADRenderError(f"文件{file_hash}正在处理中，请稍后重试")
    
    # 2. 标记为处理中
    _update_cache(file_hash, "processing")
    
    try:
        temp_filename = f"temp_{file_type}_" + file_hash[:8] + f".{file_type}"
        temp_cad_path = save_temp_file(file_content, temp_filename)
        png_path = cad_to_png(temp_cad_path, f"{temp_filename}.png")
        if not Path(png_path).exists():
            raise CADRenderError(f"CAD渲染图片失败，PNG路径不存在：{png_path}")
        
        with open(png_path, "rb") as f:
            img = Image.open(f)
            # 1. 放大2倍（解决文字太小）
            img = img.resize((img.width*2, img.height*2), Image.Resampling.LANCZOS)
            # 2. 灰度化+增强对比度（和OCR预处理对齐）
            img = img.convert("L")
            img = ImageOps.autocontrast(img, cutoff=2)
            # 3. 去噪
            img = img.filter(ImageFilter.MedianFilter(size=3))
        
            # 转成字节
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG', dpi=(300, 300))
            png_bytes = img_byte_arr.getvalue()

        try:
            os.remove(png_path)
            logger.info(f"清理临时PNG文件：{png_path}")
        except Exception as e:
            logger.warning(f"清理临时PNG文件失败：{png_path}，错误：{str(e)}")


        
        # 3. 更新缓存为成功
        _update_cache(file_hash, "success", png_bytes)
        return png_bytes
    
    except Exception as e:
        logger.error(f"CAD渲染为图片失败：{str(e)}", exc_info=True)
        _update_cache(file_hash, "failed")
        raise CADRenderError(f"CAD渲染为图片失败：{str(e)}") from e

def process_dxf_service(file_content: bytes, filename: str) -> dict:
    """处理DXF文件：渲染为图片+OCR+AI审查+报告生成"""
    file_hash = _get_file_hash(file_content)
    # 1. 检查缓存
    cache_data = _check_cache(file_hash)
    if cache_data:
        if cache_data["status"] == "success":
            logger.info(f"复用缓存结果：{file_hash}")
            return cache_data["result"]
        elif cache_data["status"] == "processing":
            raise CADRenderError(f"文件{file_hash}正在处理中，请稍后重试")
    
    # 2. 标记为处理中
    _update_cache(file_hash, "processing")
    
    # 延迟导入
    from app.services.ocr_service import perform_ocr_service
    from app.services.common_service import generate_report_service
    
    try:
        temp_dxf_path = save_temp_file(file_content, filename)
        png_file_path = cad_to_png(str(temp_dxf_path), f"temp_{filename}.png")
        if not png_file_path or not Path(png_file_path).exists():
            result = {"status": "failed", "message": "DXF文件渲染图片失败"}
            _update_cache(file_hash, "failed", result)
            return result
        
        with open(png_file_path, "rb") as f:
            png_content = f.read()

        ocr_result = perform_ocr_service(png_content, "dxf")
        if ocr_result["status"] != "success":
            _update_cache(file_hash, "failed", ocr_result)
            return ocr_result

        # 修复2：调用实例的ai_review_service方法
        ai_result = ai_service_instance.ai_review_service([ocr_result["structured_data"]], filename)
        if ai_result["status"] != "success":
            _update_cache(file_hash, "failed", ai_result)
            return ai_result

        report = generate_report_service(ai_result, filename)
        result = {
            "status": "success",
            "result": {"ocr": ocr_result, "ai_review": ai_result, "report": report},
            "message": "DXF文件处理完成"
        }
        
        _update_cache(file_hash, "success", result)
        return result
    
    except Exception as e:
        logger.error(f"DXF文件处理异常：{str(e)}", exc_info=True)
        result = {"status": "failed", "error": str(e), "message": "DXF文件处理失败"}
        _update_cache(file_hash, "failed", result)
        return result

def process_pdf_service(file_content: bytes, filename: str) -> dict:
    """处理PDF文件：提取所有页面图片+批量OCR+汇总AI审查+报告生成"""
    # 延迟导入
    from app.services.ocr_service import perform_ocr_service
    from app.services.common_service import generate_report_service
    
    try:
        # 1. PDF转图片（优化：增加参数避免中文乱码）
        images = convert_from_bytes(
            file_content,
            dpi=300,
            fmt="png",
            size=(2000, None),
            poppler_path=getattr(settings, "POPPLER_PATH", None)  # 支持配置poppler路径
        )
        if not images:
            return {"status": "failed", "message": "PDF文件无有效页面可提取"}
        
        all_ocr_structured = []
        # 2. 多页PDF循环OCR
        for idx, img in enumerate(images):
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG', dpi=(300, 300))
            img_bytes = img_byte_arr.getvalue()
            
            ocr_res = perform_ocr_service(img_bytes, "pdf")
            if ocr_res["status"] != "success":
                logger.warning(f"PDF第{idx+1}页OCR失败：{ocr_res.get('error', '未知错误')}")
                continue
            all_ocr_structured.append(ocr_res["structured_data"])
        
        if not all_ocr_structured:
            return {"status": "failed", "message": "PDF所有页面OCR识别失败"}

        # 修复3：调用实例的ai_review_service方法
        ai_result = ai_service_instance.ai_review_service(all_ocr_structured, filename)
        if ai_result["status"] != "success":
            return ai_result

        # 4. 生成报告
        report = generate_report_service(ai_result, filename)

        return {
            "status": "success",
            "result": {
                "ocr_page_count": len(all_ocr_structured), 
                "ocr": all_ocr_structured, 
                "ai_review": ai_result, 
                "report": report
            },
            "message": f"PDF文件处理完成，共识别有效页面{len(all_ocr_structured)}页"
        }
    except ImportError as e:
        logger.error(f"PDF处理依赖缺失：{str(e)}，需安装pdf2image和poppler", exc_info=True)
        return {"status": "failed", "error": str(e), "message": "PDF处理依赖未安装，请安装pdf2image和poppler"}
    except Exception as e:
        logger.error(f"PDF文件处理异常：{str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e), "message": "PDF文件处理失败"}

# ========== 通用临时文件保存函数（供全项目复用） ==========
def universal_save_temp_file(file_content: bytes, filename: str, sub_dir: str = "cad") -> str:
    """统一全项目的临时文件保存逻辑"""
    file_hash = hashlib.md5(file_content).hexdigest()[:8] 
    temp_dir = _get_project_root() / "temp" / sub_dir
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{file_hash}_{filename}"
    
    if temp_path.exists():
        logger.info(f"复用临时文件：{temp_path}")
        return str(temp_path)
    
    with open(temp_path, "wb") as f:
        f.write(file_content)
    logger.info(f"临时文件已保存：{temp_path}")
    return str(temp_path)

