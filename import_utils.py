# -*- coding: utf-8 -*-
"""多格式员工数据导入模块。

支持格式：xlsx / xls / csv / pdf / pptx / ppt
统一流程：文件 → 二维表格（表头 + 数据行）→ 智能字段映射 → 规范化员工字典。

对外主入口：
    parse_file(path) -> (headers, rows, format_name)
        headers: 原始表头列表
        rows: 原始数据行（list[list]）
    map_rows(headers, rows) -> (mapped_records, unknown_headers)
        mapped_records: 已映射到 Employee 字段并规范化的 dict 列表
"""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SUPPORTED = {".xlsx", ".xls", ".csv", ".pdf", ".pptx", ".ppt"}

# 字段 → 可能的表头别名（小写、去空格后匹配）
FIELD_ALIASES: dict[str, list[str]] = {
    "name":              ["姓名", "员工姓名", "员工", "名字", "name", "员工名称"],
    "gender":            ["性别", "gender", "sex"],
    "birth_date":        ["出生日期", "生日", "出生年月", "出生", "birthdate", "birth", "出生日期 time"],
    "hire_date":         ["入职日期", "入职时间", "入职", "参加工作时间", "hire", "hiredate", "入职日"],
    "department":        ["部门", "所属部门", "部门名称", "department", "dept", "单位", "科室"],
    "position":          ["职位", "岗位", "职务", "position", "title", "岗位名称"],
    "is_cadre":          ["是否干部", "干部", "干部标识", "iscadre", "cadre", "是否管理层", "管理岗"],
    "education":         ["学历", "文化程度", "education", "学位", "最高学历"],
    "phone":             ["电话", "手机", "手机号", "联系电话", "手机号码", "phone", "mobile", "tel"],
    "email":             ["邮箱", "电子邮件", "email", "e-mail", "mail"],
    "contract_end_date": ["合同到期", "合同到期日", "劳动合同到期", "合同截止", "合同结束日期",
                          "contractend", "contract", "到期日", "合同期限至"],
    "notes":             ["备注", "说明", "notes", "remark", "备注信息"],
}

# 反向查找表：别名 → 标准字段
_ALIAS_TO_FIELD: dict[str, str] = {}
for _field, _aliases in FIELD_ALIASES.items():
    for _a in _aliases:
        _ALIAS_TO_FIELD[_a] = _field


def _norm_header(value) -> str:
    """规范化表头：转字符串、去空白、转小写。"""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip().lower()


def normalize_date(value) -> str:
    """把各种日期表示规范成 YYYY-MM-DD 字符串；失败返回原样字符串。"""
    if value is None or value == "":
        return ""
    # Excel 序列号日期
    if isinstance(value, (int, float)):
        try:
            from openpyxl.utils.datetime import from_excel
            d = from_excel(value)
            if isinstance(d, datetime):
                return d.date().isoformat()
            if isinstance(d, date):
                return d.isoformat()
        except Exception:
            pass
        return str(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    # 统一分隔符：/ . 年 月 日 → -
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    text = re.sub(r"\s+", "", text)
    # 提取 YYYY-M-D 或 YYYY-M 形式
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if m.group(3) else 1
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return text
    return text


def normalize_bool(value) -> bool:
    """把各种表示转成布尔（是否干部）。"""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"是", "有", "y", "yes", "true", "1", "干部", "√", "✓"}


# --------------------------------------------------------------------------- #
# 各格式解析 → (headers, rows)
# --------------------------------------------------------------------------- #
def _parse_xlsx(path: Path) -> tuple[list, list[list]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
    return _split_table(all_rows)


def _parse_xls(path: Path) -> tuple[list, list[list]]:
    import xlrd
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    all_rows = [sheet.row_values(r) for r in range(sheet.nrows)]
    return _split_table(all_rows)


def _parse_csv(path: Path) -> tuple[list, list[list]]:
    raw = None
    for enc in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            raw = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ValueError("CSV 编码无法识别")
    all_rows = list(csv.reader(raw.splitlines()))
    return _split_table(all_rows)


def _parse_pdf(path: Path) -> tuple[list, list[list]]:
    import pdfplumber
    with pdfplumber.open(str(path)) as pdf:
        # 优先走真正的表格线提取
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                if table and len(table) >= 2:
                    return _split_table(table)
        # 无表格线：用单词坐标按行聚类、按 x 间隙分列（适配排版型花名册）
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            if not words:
                continue
            # 按 top 聚类成行（容差 3pt）
            lines: dict[int, list] = {}
            for w in words:
                key = round(w["top"] / 3) * 3
                lines.setdefault(key, []).append(w)
            parsed = []
            for key in sorted(lines):
                line = sorted(lines[key], key=lambda w: w["x0"])
                cols: list[str] = []
                buffer = [line[0]]
                for prev, cur in zip(line, line[1:]):
                    # 相邻词水平间隙较大 → 新列
                    if cur["x0"] - prev["x1"] > 9:
                        cols.append(" ".join(x["text"] for x in buffer))
                        buffer = [cur]
                    else:
                        buffer.append(cur)
                cols.append(" ".join(x["text"] for x in buffer))
                parsed.append(cols)
            if len(parsed) >= 2 and max(len(r) for r in parsed) >= 2:
                return _split_table(parsed)
    raise ValueError("PDF 中未找到可识别的表格，建议使用 xlsx/csv 格式")


def _parse_pptx(path: Path) -> tuple[list, list[list]]:
    from pptx import Presentation
    prs = Presentation(str(path))
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_table:
                table = shape.table
                rows = []
                for r in table.rows:
                    rows.append([cell.text for cell in r.cells])
                if len(rows) >= 2:
                    return _split_table(rows)
    raise ValueError("PPTX 中未找到可识别的表格")


def _parse_ppt(path: Path) -> tuple[list, list[list]]:
    """老版 .ppt 二进制格式：优先用 LibreOffice 转 pptx 再解析。"""
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("libreoffice") and not shutil.which("soffice"):
        raise ValueError("老版 .ppt 需要 LibreOffice 支持，请先另存为 .pptx 后再导入")
    tmpdir = tempfile.mkdtemp()
    cmd = shutil.which("libreoffice") or shutil.which("soffice")
    subprocess.run(
        [cmd, "--headless", "--convert-to", "pptx", "--outdir", tmpdir, str(path)],
        check=True, capture_output=True, timeout=120,
    )
    converted = Path(tmpdir) / (path.stem + ".pptx")
    if not converted.exists():
        raise ValueError("PPT 转换失败，请另存为 .pptx 后再导入")
    return _parse_pptx(converted)


def _split_table(all_rows: list[list]) -> tuple[list, list[list]]:
    """去掉全空行，第一行作为表头，其余作为数据。"""
    cleaned = []
    for row in all_rows:
        if row and any(c is not None and str(c).strip() for c in row):
            cleaned.append(["" if c is None else str(c).strip() for c in row])
    if not cleaned:
        return [], []
    header = cleaned[0]
    body = [r for r in cleaned[1:] if any(str(c).strip() for c in r)]
    return header, body


def parse_file(path: str | Path) -> tuple[list, list[list], str]:
    """解析文件，返回 (headers, rows, 格式名)。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"不支持的格式：{ext}，支持：{', '.join(sorted(SUPPORTED))}")
    parsers = {
        ".xlsx": _parse_xlsx, ".xls": _parse_xls, ".csv": _parse_csv,
        ".pdf": _parse_pdf, ".pptx": _parse_pptx, ".ppt": _parse_ppt,
    }
    headers, rows = parsers[ext](path)
    return headers, rows, ext.lstrip(".")


# --------------------------------------------------------------------------- #
# 字段映射
# --------------------------------------------------------------------------- #
def map_rows(headers: list, rows: list[list]) -> tuple[list[dict], list[str]]:
    """把原始表格映射到员工字段。

    返回 (records, unknown_headers)。
    records 中每条为 {字段名: 值}，未识别的列记录在 unknown_headers。
    """
    field_of_col: dict[int, str] = {}
    unknown: list[str] = []
    for idx, h in enumerate(headers):
        norm = _norm_header(h)
        field = _ALIAS_TO_FIELD.get(norm)
        if field is None:
            # 宽松匹配：别名是表头的子串或反之
            for alias, f in _ALIAS_TO_FIELD.items():
                if alias and (alias in norm or norm in alias):
                    field = f
                    break
        if field:
            field_of_col[idx] = field
        else:
            unknown.append(str(h))

    date_fields = {"birth_date", "hire_date", "contract_end_date"}
    records: list[dict] = []
    for row in rows:
        rec: dict = {}
        for idx, field in field_of_col.items():
            if idx >= len(row):
                continue
            val = row[idx]
            if val is None or str(val).strip() == "":
                continue
            if field in date_fields:
                val = normalize_date(val)
            elif field == "is_cadre":
                val = normalize_bool(val)
            elif field == "gender":
                g = str(val).strip()
                val = "男" if g.startswith("男") else ("女" if g.startswith("女") else g)
            rec[field] = val
        if rec.get("name"):  # 姓名非空才算有效记录
            records.append(rec)
    return records, unknown
