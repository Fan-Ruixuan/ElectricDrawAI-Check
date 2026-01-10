import sys
import os
import io
from pdf2image import convert_from_bytes  # PDF转图片需用到
import subprocess
import logging
from pathlib import Path
from typing import Optional
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from app.services.ocr_service import perform_ocr_service
from app.services.ai_service import ai_review_service
from app.services.common_service import generate_report_service
from pdf2image import convert_from_bytes

# 从utiils导入
from app.utils.file_utils import save_temp_file, _get_project_root

#从core导入
from app.core.config import settings

logger = logging.getLogger(__name__)



# 定义自定义异常类
class CADConversionError(Exception):
    """CAD文件转换过程中发生的错误"""
    pass

class CADRenderError(Exception):
    """CAD文件渲染为PNG过程中发生的错误"""
    pass

def process_image_service (file_content: bytes, filename: str) -> dict:
    """处理图片文件的业务逻辑"""
    try:
        # 调用 OCR 服务
        ocr_result = perform_ocr_service (file_content, "image")
        if ocr_result ["status"] != "success":
            return ocr_result # 直接返回错误结果
        # 调用 AI 审查服务
        ai_result = ai_review_service([ocr_result["structured_data"]], filename)
        if ai_result ["status"] != "success":
            return ai_result # 直接返回错误结果
        # 调用报告生成服务
        report = generate_report_service (ai_result, filename)
        return{
            "status": "success",
            "result": {
                "ocr": ocr_result,
                "ai_review": ai_result,
                "report": report
            },
            "message": "图片文件处理完成"    
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str (e),
            "message": "图片文件处理失败"
        }




"""以下内容：[AI辅助生成]CAD 服务模块
本模块负责处理 CAD 文件的转换和渲染。
其中，convert_dwg_to_dxf_from_path 函数的核心逻辑已通过 AI 辅助重构，
将一个复杂的大函数拆分为多个职责单一的小函数，极大提升代码的可读性、可维护性和可测试性."""

def _validate_dwg_exists(dwg_file_path: str) -> Path:
    """
    Validate that the DWG file exists and return its Path.
    Raises FileNotFoundError if missing.
    """
    dwg_path = Path(dwg_file_path)
    if not dwg_path.exists():
        logger.error("DWG file not found: %s", dwg_file_path)
        raise FileNotFoundError(f"DWG file not found: {dwg_file_path}")
    return dwg_path


def _get_and_validate_converter_path() -> Path:
    """
    Get ODA converter path from settings and validate it exists.
    Raises FileNotFoundError if missing.
    """
    converter_path_str = settings.ODA_CONVERTER_PATH
    converter_path = Path(converter_path_str)
    if not converter_path.exists():
        logger.error("ODA converter not found at %s", converter_path)
        raise FileNotFoundError(f"ODA converter not found: {converter_path}")
    return converter_path


def _determine_output_dxf_path(dwg_path: Path, output_dxf_path: Optional[str]) -> Path:
    if output_dxf_path:
        out_path = Path(output_dxf_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        project_root = _get_project_root()
        out_folder = project_root / "temp" / "output"
        out_folder.mkdir(parents=True, exist_ok=True)
        # 确保正确处理文件名
        dxf_filename = dwg_path.stem + ".dxf"
        out_path = out_folder / dxf_filename
    return out_path


def _build_oda_converter_command(converter_path: Path, input_folder: str, output_folder: str) -> list:
    """
    Build the command string to invoke ODAFileConverter.
    """
    return [
        str(converter_path),
        input_folder,
        output_folder,
        settings.ODA_TARGET_VERSION,
        settings.ODA_OUTPUT_FORMAT,
        settings.ODA_OTHER_PARAM_1,
        settings.ODA_OTHER_PARAM_2
    ]



"""[以下单个函数由 github Copilot 优化完善，提高代码健壮性]"""
def extract_layers_from_dxf(dxf_file_path: str, target_layers: list = None) -> dict:
    """从 DXF 文件中提取指定图层的所有实体。
    Args:
        dxf_file_path: DXF 文件的路径。
        target_layers: 需要提取的图层名称列表。如果为 None，则提取所有图层。
    Returns:
        一个字典，键是图层名称，值是该图层上所有实体的列表，每个实体包含其类型和基本属性。
    """
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
        print(f"DEBUG: 读取DXF文件错误详情: {str(e)}")  # 临时打印错误信息，便于调试    
        logger.exception("读取 DXF 文件失败: %s", dxf_path)
        raise CADConversionError(f"读取 DXF 文件失败: {dxf_path}") from e

    extracted_data = {}
    for entity in msp:
        try:
            entity_layer = entity.dxf.layer
        except Exception:
            # Skip entities without layer info
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
    """
    Convert a .dwg file to .dxf using ODAFileConverter.
    Orchestrates validation, path resolution, command construction and execution.
    Returns the absolute path to the generated .dxf file.
    """
    dwg_path = _validate_dwg_exists(dwg_file_path)
    converter_path = _get_and_validate_converter_path()
    out_path = _determine_output_dxf_path(dwg_path, output_dxf_path)

    input_folder = str(dwg_path.parent)
    output_folder = str(out_path.parent)
    cmd = _build_oda_converter_command(converter_path, input_folder, output_folder)

    logger.debug("Executing ODAFileConverter: %s", cmd)
    print(f"执行的命令: {cmd}")  # 临时打印命令，便于调试

    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=300
        )

    except subprocess.TimeoutExpired as e:
        print(f"DEBUG: ODAFileConverter 超时错误详情: {str(e)}")  # 临时打印错误信息，便于调试
        logger.exception("ODAFileConverter timed out")
        raise CADConversionError("ODAFileConverter timed out") from e
    except Exception as e:
        print(f"DEBUG: 执行ODAFileConverter错误详情: {str(e)}")  # 临时打印错误信息，便于调试
        logger.exception("Failed to execute ODAFileConverter")
        raise CADConversionError("Failed to execute ODAFileConverter") from e

    print(f"DEBUG: out_path is {out_path}")
    print(f"DEBUG: out_path.exists() is {out_path.exists()}")

    if result.returncode == 0 and out_path.exists():
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
        raise CADConversionError(f"DWG conversion failed: {result.stderr or result.stdout}")

def convert_dwg_to_dxf_from_bytes(file_content: bytes, filename: str) -> dict:
    """将二进制的 DWG 文件内容转换为 DXF"""
    # 1. 将二进制内容保存为临时文件（先定义变量，再判断）
    temp_file_path = save_temp_file(file_content, filename)
    
    # 2. 检查临时文件是否存在（exists是方法，需要加括号）
    if not Path(temp_file_path).exists():
        raise FileNotFoundError(f"临时文件{temp_file_path}未成功创建")
    
    # 3. 直接调用之前优化好的函数(调用 ODA 转换器进行格式转换)
    dxf_file_path = convert_dwg_to_dxf_from_path(str(temp_file_path))  # 确保传入字符串路径
    
    # 4. 返回结果（补充status字段，和其他服务统一）
    return {
        "status": "success",
        "dxf_file": os.path.basename(dxf_file_path), 
        "original_filename": filename,
        "dxf_file_path": dxf_file_path  # 新增路径字段，方便后续使用
    }



def cad_to_png(cad_file_path: str, output_png_path: str = "temp_cad_render.png") -> str:
    """
    Convert a CAD file (.dwg/.dxf) to a PNG image.
    - If input is .dwg, it will be converted to .dxf via convert_dwg_to_dxf_from_path.
    Returns absolute path to the generated PNG.
    """
    from ezdxf import DXFError  # local import to keep module-level imports light
    import matplotlib.pyplot as plt

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
        print(f"DEBUG: 无效的DXF/CAD文件错误详情: {str(e)}")  # 临时打印错误信息，便于调试
        logger.exception("Invalid DXF/CAD file: %s", cad_path)
        raise CADRenderError(f"Invalid DXF/CAD file: {cad_path}") from e
    except Exception as e:
        print(f"DEBUG: 读取CAD文件错误详情: {str(e)}")  # 临时打印错误信息，便于调试
        logger.exception("Failed to read CAD file: %s", cad_path)
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
        # if user passed a relative path, keep it relative to project root for consistency
        if not out_path.is_absolute():
            out_path = _get_project_root() / out_path
            out_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(
            str(out_path),
            dpi=settings.CAD_RENDER_DPI,  # 使用配置的高精度DPI
            bbox_inches="tight",
            pad_inches=0
        )
        plt.close(fig)
        logger.info("CAD rendered to PNG: %s", out_path)
        return str(out_path.resolve())

    except Exception as e:
        print(f"DEBUG: 渲染错误详情: {str(e)}")  # 临时打印错误信息，便于调试
        logger.exception("Failed to render CAD to PNG")
        raise CADRenderError("Failed to render CAD to PNG") from e


def process_dxf_service(file_content: bytes, filename: str) -> dict:
    """处理DXF文件：渲染为图片+OCR+AI审查+报告生成"""
    try:
        # 1. 先保存DXF二进制内容为临时文件（因为cad_to_png需要文件路径）
        temp_dxf_path = save_temp_file(file_content, filename)
        
        # 2. DXF转PNG（传入临时文件路径，而非二进制）
        png_file_path = cad_to_png(str(temp_dxf_path), f"temp_{filename}.png")
        if not png_file_path or not Path(png_file_path).exists():
            return {"status": "failed", "message": "DXF文件渲染图片失败"}
        
        # 3. 读取PNG文件为二进制（适配OCR服务入参）
        with open(png_file_path, "rb") as f:
            png_content = f.read()

        # 4. 调用OCR服务，文件类型标记为dxf便于后续区分
        ocr_result = perform_ocr_service(png_content, "dxf")
        if ocr_result["status"] != "success":
            return ocr_result

        # 5. AI审查（补充drawing_name参数，适配函数定义）
        ai_result = ai_review_service([ocr_result["structured_data"]], filename)
        if ai_result["status"] != "success":
            return ai_result

        # 6. 生成报告
        report = generate_report_service(ai_result, filename)

        return {
            "status": "success",
            "result": {"ocr": ocr_result, "ai_review": ai_result, "report": report},
            "message": "DXF文件处理完成"
        }
    except Exception as e:
        logger.error(f"DXF文件处理异常：{str(e)}")
        return {"status": "failed", "error": str(e), "message": "DXF文件处理失败"}


def process_pdf_service(file_content: bytes, filename: str) -> dict:
    """处理PDF文件：提取所有页面图片+批量OCR+汇总AI审查+报告生成"""
    try:
        # 1. PDF转图片（依赖pdf2image，需确保已安装poppler）
        images = convert_from_bytes(file_content)
        if not images:
            return {"status": "failed", "message": "PDF文件无有效页面可提取"}
        
        all_ocr_structured = []
        # 2. 多页PDF循环做OCR
        for idx, img in enumerate(images):
            # 图片转bytes（适配perform_ocr_service入参）
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            ocr_res = perform_ocr_service(img_bytes, "pdf")
            if ocr_res["status"] != "success":
                logger.warning(f"PDF第{idx+1}页OCR失败：{ocr_res.get('error')}")
                continue
            all_ocr_structured.append(ocr_res["structured_data"])
        
        if not all_ocr_structured:
            return {"status": "failed", "message": "PDF所有页面OCR识别失败"}

        # 3. 汇总OCR结果做AI审查
        ai_result = ai_review_service(all_ocr_structured, filename)
        if ai_result["status"] != "success":
            return ai_result

        # 4. 生成报告
        report = generate_report_service(ai_result, filename)

        return {
            "status": "success",
            "result": {"ocr_page_count": len(all_ocr_structured), "ocr": all_ocr_structured, "ai_review": ai_result, "report": report},
            "message": f"PDF文件处理完成，共识别有效页面{len(all_ocr_structured)}页"
        }
    except ImportError as e:
        logger.error(f"PDF处理依赖缺失：{str(e)}，需安装pdf2image和poppler")
        return {"status": "failed", "error": str(e), "message": "PDF处理依赖未安装，请安装pdf2image"}
    except Exception as e:
        logger.error(f"PDF文件处理异常：{str(e)}")
        return {"status": "failed", "error": str(e), "message": "PDF文件处理失败"}


def render_cad_to_image(dxf_file_path: str) -> str:
    """
    将DXF文件渲染为图片
    :param dxf_file_path: DXF文件的路径
    :return: 生成的图片文件路径
    """
    # 1. 这里需要实现DXF到图片的渲染逻辑
    # 2. 可以使用 ezdxf、matplotlib 等库来读取并渲染DXF文件
    # 3. 将渲染结果保存为图片，例如PNG格式
    # 4. 返回图片的路径
    pass

"""TODO: [未来优化] 考虑与 extract_layers_from_dxf 函数集成
集成后，该函数可返回一个包含 "png_path" 和 "extracted_layers" 的字典，
以在一次调用中同时获取图片和结构化数据，提高效率."""


    


