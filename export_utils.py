# -*- coding: utf-8 -*-
"""员工花名册导出模块 —— 导出到 xlsx / csv。

对外主入口：
    export_employees(employees, path) -> None
        path 后缀决定格式：.xlsx / .csv
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from models import Employee

# 导出列：(表头, 取值函数)
COLUMNS: list[tuple[str, object]] = [
    ("姓名", lambda e, r: e.name),
    ("性别", lambda e, r: e.gender),
    ("出生日期", lambda e, r: e.birth_date),
    ("年龄", lambda e, r: e.age(r) if e.age(r) is not None else ""),
    ("入职日期", lambda e, r: e.hire_date),
    ("工龄(年)", lambda e, r: e.tenure(r) if e.tenure(r) is not None else ""),
    ("部门", lambda e, r: e.department),
    ("职位", lambda e, r: e.position),
    ("是否干部", lambda e, r: "是" if e.is_cadre else "否"),
    ("学历", lambda e, r: e.education),
    ("电话", lambda e, r: e.phone),
    ("邮箱", lambda e, r: e.email),
    ("合同到期日", lambda e, r: e.contract_end_date),
    ("状态", lambda e, r: "已离职" if e.is_departed else "在职"),
    ("离职日期", lambda e, r: e.leave_date),
    ("备注", lambda e, r: e.notes),
]


def _rows(employees: list[Employee], ref: date):
    for e in employees:
        yield [fn(e, ref) for _, fn in COLUMNS]


def export_employees(employees: list[Employee], path: str | Path,
                     ref: date | None = None) -> None:
    """按 path 后缀导出员工列表，支持 .xlsx 与 .csv。"""
    ref = ref or date.today()
    path = Path(path)
    suffix = path.suffix.lower()
    headers = [h for h, _ in COLUMNS]

    if suffix == ".csv":
        # utf-8-sig 让 Excel 直接打开不乱码
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(_rows(employees, ref))
        return

    if suffix == ".xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = Workbook()
        ws = wb.active
        ws.title = "员工花名册"
        ws.append(headers)

        # 表头样式
        header_fill = PatternFill("solid", fgColor="2F6FED")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        thin = Side(style="thin", color="D0D7E5")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        for row in _rows(employees, ref):
            ws.append(row)

        # 数据区样式 + 隔行底色
        alt_fill = PatternFill("solid", fgColor="F4F7FE")
        for r in range(2, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if r % 2 == 0:
                    cell.fill = alt_fill

        # 列宽
        widths = [12, 8, 13, 8, 13, 10, 14, 14, 10, 12, 15, 22, 13, 9, 13, 24]
        from openpyxl.utils import get_column_letter
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 24

        wb.save(path)
        return

    raise ValueError(f"不支持的导出格式：{suffix}（仅支持 .xlsx / .csv）")
