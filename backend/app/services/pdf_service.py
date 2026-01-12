# app/services/pdf_service.py
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import os
from datetime import datetime

# 注册中文字体，解决PDF中文乱码问题
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
FONT_CN = 'STSong-Light'

def generate_review_pdf(review_result: dict, filename: str = None) -> str:
    """
    生成AI审查结果PDF报告
    :param review_result: ai_review_service返回的审查结果字典
    :param filename: 原图纸文件名
    :return: PDF文件的本地路径
    """
    # 创建输出目录，不存在则自动创建
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    # 生成带时间戳的PDF文件名，避免重复
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.splitext(filename)[0] if filename else "unnamed_drawing"
    pdf_filename = f"review_{base_name}_{timestamp}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)

    # 初始化PDF文档和样式
    doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                            rightMargin=0.5*inch, leftMargin=0.5*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()
    # 自定义中文样式，适配字体和行距
    cn_title_style = styles["Title"]
    cn_title_style.fontName = FONT_CN
    cn_title_style.fontSize = 16
    cn_title_style.alignment = 1  # 居中

    cn_heading_style = styles["Heading2"]
    cn_heading_style.fontName = FONT_CN
    cn_heading_style.fontSize = 12
    cn_heading_style.spaceAfter = 8

    cn_body_style = styles["BodyText"]
    cn_body_style.fontName = FONT_CN
    cn_body_style.fontSize = 10
    cn_body_style.leading = 14  # 行距

    story = []  # PDF内容容器

    # 1. 添加报告标题
    story.append(Paragraph("图纸AI审查报告", cn_title_style))
    story.append(Spacer(1, 0.3*inch))

    # 2. 添加基础信息
    story.append(Paragraph("一、基础信息", cn_heading_style))
    story.append(Paragraph(f"审查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", cn_body_style))
    story.append(Paragraph(f"原图纸文件：{filename or '未知文件'}", cn_body_style))
    story.append(Spacer(1, 0.2*inch))

    # 3. 添加核心审查结果
    story.append(Paragraph("二、AI审查结果", cn_heading_style))
    if "structured_data" in review_result and review_result["structured_data"]:
        # 按行分割内容，保持原格式
        content_lines = review_result["structured_data"].split('\n')
        for line in content_lines:
            line = line.strip() if line.strip() else " "  # 处理空行，避免PDF排版异常
            story.append(Paragraph(line, cn_body_style))
    else:
        story.append(Paragraph("暂无有效审查结果", cn_body_style))

    # 4. 构建PDF文档
    try:
        doc.build(story)
        return pdf_path
    except Exception as e:
        raise Exception(f"PDF生成失败：{str(e)}")

# 测试代码（可选，直接运行该文件可验证功能）
if __name__ == "__main__":
    test_result = {
        "status": "success",
        "structured_data": "总体结论：通过\n图纸编号：DQ-2026-008（符合规范）\n图纸比例：1:50（符合要求）\n设备型号：CM1-250（标注清晰）\n电线规格：BV-4mm²（选型合理）"
    }
    path = generate_review_pdf(test_result, "低压电气图纸.pdf")
    print(f"PDF生成成功，路径：{path}")