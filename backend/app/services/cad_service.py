import sys
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional
import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

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


"""[AI辅助生成]CAD 服务模块
本模块负责处理 CAD 文件的转换和渲染。
其中，convert_dwg_to_dxf_from_path 函数的核心逻辑已通过 AI 辅助重构，
将一个复杂的大函数拆分为多个职责单一的小函数，极大提升代码的可读性、可维护性和可测试性。"""


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
    # 1. 将二进制内容保存为临时文件
    temp_file_path = save_temp_file(file_content, filename)
    # 2. 直接调用之前优化好的函数(调用 ODA 转换器进行格式转换)
    dxf_file_path = convert_dwg_to_dxf_from_path(temp_file_path)
    # 3. 返回结果
    return {"dxf_file": os.path.basename(dxf_file_path), "original_filename": filename}



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

"""TODO: [未来优化] 考虑与 extract_layers_from_dxf 函数集成
集成后，该函数可返回一个包含 "png_path" 和 "extracted_layers" 的字典，
以在一次调用中同时获取图片和结构化数据，提高效率."""


    


