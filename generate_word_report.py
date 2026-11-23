import os
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

MD_FILENAME = "AutoCare_Project_Documentation.md"
OUTPUT_DOCX = "AutoCare_Project_Documentation_Report.docx"

DIAGRAM_FILES = [
    ("docs/diagrams/architecture.png", "Figure 3.1 - AutoCare Layered Component & Blueprint Architecture"),
    ("docs/diagrams/erd.png", "Figure 3.2 - Entity-Relationship Diagram (ERD) of the 14-Table SQLite Schema"),
    ("docs/diagrams/dfd_level0.png", "Figure 3.3 - Zero-Level Data Flow Diagram (Context Diagram)"),
    ("docs/diagrams/dfd_level1.png", "Figure 3.4 - First-Level Data Flow Diagram (Domain Processes & Data Stores)"),
    ("docs/diagrams/workflow_flowchart.png", "Figure 3.5 - End-to-End Operational & Razorpay Visit-Payment Gate Flowchart"),
]

# Search common locations so the script works from any folder in Downloads
BASE_DIRS = [
    os.getcwd(),
    os.path.join(os.getcwd(), "AutoCare_Documentation"),
    os.path.abspath(os.path.join(os.getcwd(), "..")),
    os.path.abspath(os.path.join(os.getcwd(), "..", "AutoCare_Documentation")),
    os.path.expanduser(r"~\Downloads"),
    os.path.expanduser(r"~\Downloads\AutoCare_Documentation"),
    os.path.expanduser(r"~\Downloads\AutoCare_Documentation\AutoCare_Documentation"),
]


def resolve_path(rel_path):
    rel_norm = rel_path.replace("/", os.sep).replace("\\", os.sep)
    for base in BASE_DIRS:
        candidate = os.path.join(base, rel_norm)
        if os.path.isfile(candidate):
            return candidate
    return None


def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for side, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{side}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def add_page_number(run):
    fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls('w'))
    instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> PAGE </w:instrText>' % nsdecls('w'))
    fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls('w'))
    fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls('w'))
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)


def format_inline_markdown(paragraph, text):
    token_pattern = re.compile(r'(\*\*.*?\*\*|\*[^\*]+?\*|`[^`]+?`)')
    tokens = token_pattern.split(text)
    for token in tokens:
        if not token:
            continue
        if token.startswith('**') and token.endswith('**'):
            r = paragraph.add_run(token[2:-2])
            r.bold = True
        elif token.startswith('*') and token.endswith('*'):
            r = paragraph.add_run(token[1:-1])
            r.italic = True
        elif token.startswith('`') and token.endswith('`'):
            r = paragraph.add_run(token[1:-1])
            r.font.name = 'Consolas'
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(0x8B, 0x26, 0x1D)
        else:
            paragraph.add_run(token)


def insert_image_or_placeholder(doc, img_rel_path, alt_text, max_width_inches=6.0):
    resolved = resolve_path(img_rel_path)
    if resolved:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run()
        run.add_picture(resolved, width=Inches(max_width_inches))

        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_after = Pt(10)
        r_cap = cap.add_run(f"[{alt_text} - {img_rel_path}]")
        r_cap.italic = True
        r_cap.font.size = Pt(9)
        r_cap.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    else:
        tbl = doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = tbl.cell(0, 0)
        set_cell_background(cell, "F8F9FA")
        set_cell_margins(cell, top=200, bottom=200, left=200, right=200)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p.add_run(f"[ SCREENSHOT PLACEHOLDER: {alt_text} ]\n")
        r1.bold = True
        r1.font.size = Pt(10)
        r1.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        r2 = p.add_run(f"Expected path: {img_rel_path}")
        r2.italic = True
        r2.font.size = Pt(9)
        r2.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        doc.add_paragraph()


def render_markdown_table(doc, table_lines):
    rows_data = []
    for idx, line in enumerate(table_lines):
        stripped = line.strip().strip('|')
        cells = [c.strip() for c in stripped.split('|')]
        if idx == 1 and all(re.match(r'^:?-{2,}:?$', c.replace(' ', '')) for c in cells):
            continue
        rows_data.append(cells)

    if not rows_data:
        return

    num_cols = max(len(r) for r in rows_data)
    table = doc.add_table(rows=len(rows_data), cols=num_cols)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for r_idx, row_values in enumerate(rows_data):
        row = table.rows[r_idx]
        for c_idx in range(num_cols):
            cell = row.cells[c_idx]
            val = row_values[c_idx] if c_idx < len(row_values) else ""
            set_cell_margins(cell, top=75, bottom=75, left=100, right=100)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            format_inline_markdown(p, val)

            if r_idx == 0:
                set_cell_background(cell, "1F4E79")
                for run in p.runs:
                    run.bold = True
                    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    run.font.size = Pt(9.5)
            else:
                if r_idx % 2 == 0:
                    set_cell_background(cell, "F2F5F8")
                for run in p.runs:
                    if not run.font.size:
                        run.font.size = Pt(9.5)

    doc.add_paragraph()


def build_title_page(doc):
    for _ in range(2):
        doc.add_paragraph()

    p_tag = doc.add_paragraph()
    p_tag.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_tag = p_tag.add_run("COMPREHENSIVE TECHNICAL & ACADEMIC PROJECT REPORT")
    r_tag.bold = True
    r_tag.font.size = Pt(11)
    r_tag.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(12)
    p_title.paragraph_format.space_after = Pt(6)
    r_title = p_title.add_run("AutoCare Garage Management System")
    r_title.bold = True
    r_title.font.size = Pt(26)
    r_title.font.color.rgb = RGBColor(0x0F, 0x2C, 0x59)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(24)
    r_sub = p_sub.add_run(
        "Full-Stack Automotive Workshop ERP with Razorpay Test Mode UPI Gate, "
        "Job Cards, Estimates, PDF Invoicing & Automated Multi-Channel Notification Logs"
    )
    r_sub.italic = True
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    meta_rows = [
        ("Repository Package", "AutoCare_Garage_Deployment_Ready"),
        ("Core Stack", "Python 3 - Flask (Application Factory + 6 Blueprints) - SQLite 3 (14 Tables)"),
        ("Frontend & Reporting", "Jinja2 Templates (20 Views) - HTML5 / CSS3 / Vanilla JS - ReportLab PDF"),
        ("Integrations", "Razorpay (Test Mode UPI / Checkout + HMAC Webhooks) - SMTP - Twilio SMS/WhatsApp"),
        ("Submitted By", "Ahsaan Ans (Master of Computer Applications - MCA)"),
        ("Institution", "Bharati Vidyapeeth's Institute of Management and Entrepreneurship Development (IMED), Pune"),
        ("Report Date", "17 October 2026"),
    ]
    tbl = doc.add_table(rows=len(meta_rows), cols=2)
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for idx, (k, v) in enumerate(meta_rows):
        c0, c1 = tbl.rows[idx].cells[0], tbl.rows[idx].cells[1]
        set_cell_margins(c0, 90, 90, 140, 140)
        set_cell_margins(c1, 90, 90, 140, 140)
        set_cell_background(c0, "EAF0F6")
        r_k = c0.paragraphs[0].add_run(k)
        r_k.bold = True
        r_k.font.size = Pt(10)
        r_v = c1.paragraphs[0].add_run(v)
        r_v.font.size = Pt(10)

    doc.add_page_break()


def convert_markdown_to_word():
    md_path = resolve_path(MD_FILENAME)
    if not md_path:
        print("ERROR: Could not find AutoCare_Project_Documentation.md!")
        print("Please make sure AutoCare_Documentation.zip is extracted in your Downloads folder or current folder.")
        return

    # Add the directory where the MD file lives to BASE_DIRS so relative docs/ paths resolve
    md_dir = os.path.dirname(os.path.abspath(md_path))
    if md_dir not in BASE_DIRS:
        BASE_DIRS.insert(0, md_dir)

    print(f"Reading Markdown from: {md_path}")
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_hdr = header.add_run("AutoCare Garage Management System - Project Documentation Report")
        r_hdr.font.size = Pt(8.5)
        r_hdr.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_ftr = footer.add_run("Page ")
        r_ftr.font.size = Pt(9)
        add_page_number(r_ftr)

    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(11)

    build_title_page(doc)

    i = 0
    mermaid_idx = 0
    while i < len(lines) and not lines[i].startswith("## Table of Contents"):
        i += 1

    while i < len(lines):
        line = lines[i]

        if line.strip() == "---":
            i += 1
            continue

        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip().lower()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1

            if lang == "mermaid":
                if mermaid_idx < len(DIAGRAM_FILES):
                    diag_path, diag_caption = DIAGRAM_FILES[mermaid_idx]
                    mermaid_idx += 1
                    insert_image_or_placeholder(doc, diag_path, diag_caption, max_width_inches=6.1)
                continue
            else:
                tbl = doc.add_table(rows=1, cols=1)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                cell = tbl.cell(0, 0)
                set_cell_background(cell, "F4F6F8")
                set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run("\n".join(code_lines))
                r.font.name = "Consolas"
                r.font.size = Pt(8.5)
                doc.add_paragraph()
                continue

        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            render_markdown_table(doc, table_lines)
            continue

        img_match = re.match(r'^!\[(.*?)\]\((.*?)\)\s*$', line.strip())
        if img_match:
            alt_text, img_path = img_match.group(1), img_match.group(2)
            insert_image_or_placeholder(doc, img_path, alt_text, max_width_inches=6.0)
            i += 1
            continue

        if line.startswith("# "):
            if line.startswith("# Chapter") or line.startswith("# Appendix"):
                doc.add_page_break()
            h = doc.add_heading(line[2:].strip(), level=1)
            for r in h.runs:
                r.font.color.rgb = RGBColor(0x0F, 0x2C, 0x59)
            i += 1
            continue
        elif line.startswith("## "):
            h = doc.add_heading(line[3:].strip(), level=2)
            for r in h.runs:
                r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
            i += 1
            continue
        elif line.startswith("### "):
            h = doc.add_heading(line[4:].strip(), level=3)
            for r in h.runs:
                r.font.color.rgb = RGBColor(0x2E, 0x6B, 0x9E)
            i += 1
            continue

        if line.strip().startswith(">"):
            quote_text = line.strip().lstrip(">").strip()
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.35)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(6)
            format_inline_markdown(p, quote_text)
            for r in p.runs:
                r.italic = True
                r.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
            i += 1
            continue

        bullet_match =re.match(r'^(\s*)[*\-]\s+(.*)$', line)
        num_match = re.match(r'^(\s*)\d+\.\s+(.*)$', line)
        if bullet_match:
            p = doc.add_paragraph(style='List Bullet')
            format_inline_markdown(p, bullet_match.group(2))
            i += 1
            continue
        elif num_match:
            p = doc.add_paragraph(style='List Number')
            format_inline_markdown(p, num_match.group(2))
            i += 1
            continue

        if line.strip():
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            format_inline_markdown(p, line.strip())

        i += 1

    out_path = os.path.abspath(OUTPUT_DOCX)
    doc.save(out_path)
    print(f"\n[SUCCESS] Word report generated at:\n{out_path}")


if __name__ == "__main__":
    convert_markdown_to_word()
