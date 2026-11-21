# -*- coding: utf-8 -*-
"""员工花名册 —— 数据模型与本地数据库（SQLite）。

对外提供：
- Employee：员工数据类，附带 age() / tenure() 便捷方法
- Database：员工记录的增删改查封装
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "employees.db"

GENDERS = ("男", "女")
EDUCATIONS = ("博士", "硕士", "本科", "大专", "高中及以下", "其他")


@dataclass
class Employee:
    id: Optional[int] = None
    name: str = ""
    gender: str = "男"
    birth_date: str = ""      # YYYY-MM-DD
    hire_date: str = ""       # YYYY-MM-DD
    department: str = ""
    position: str = ""
    is_cadre: bool = False
    education: str = ""
    phone: str = ""
    email: str = ""
    contract_end_date: str = ""   # 劳动合同到期日 YYYY-MM-DD
    is_departed: bool = False     # 是否已离职
    leave_date: str = ""          # 离职日期 YYYY-MM-DD
    notes: str = ""

    @staticmethod
    def _parse(value: str) -> Optional[date]:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def age(self, ref: Optional[date] = None) -> Optional[int]:
        """按生日计算周岁年龄；生日缺失或非法时返回 None。"""
        born = self._parse(self.birth_date)
        if born is None:
            return None
        ref = ref or date.today()
        return ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))

    def tenure(self, ref: Optional[date] = None) -> Optional[float]:
        """按入职日期计算工龄（年，保留 1 位小数）。"""
        hired = self._parse(self.hire_date)
        if hired is None:
            return None
        ref = ref or date.today()
        days = (ref - hired).days
        if days < 0:
            return None
        return round(days / 365.25, 1)

    def contract_status(self, ref: Optional[date] = None,
                        warn_days: int = 30) -> tuple[str, Optional[int]]:
        """合同到期状态。

        返回 (状态, 剩余天数)。状态取值：
        - 'none'      未填写到期日
        - 'expired'   已过期
        - 'warning'   即将到期（warn_days 天内）
        - 'normal'    正常
        """
        end = self._parse(self.contract_end_date)
        if end is None:
            return "none", None
        ref = ref or date.today()
        remaining = (end - ref).days
        if remaining < 0:
            return "expired", remaining
        if remaining <= warn_days:
            return "warning", remaining
        return "normal", remaining


class Database:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS employees (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    name              TEXT NOT NULL,
                    gender            TEXT,
                    birth_date        TEXT,
                    hire_date         TEXT,
                    department        TEXT,
                    position          TEXT,
                    is_cadre          INTEGER DEFAULT 0,
                    education         TEXT,
                    phone             TEXT,
                    email             TEXT,
                    contract_end_date TEXT,
                    is_departed       INTEGER DEFAULT 0,
                    leave_date        TEXT,
                    notes             TEXT
                )
                """
            )
            # 旧库平滑迁移：补齐后加的列
            existing = {r["name"] for r in conn.execute("PRAGMA table_info(employees)")}
            if "contract_end_date" not in existing:
                conn.execute("ALTER TABLE employees ADD COLUMN contract_end_date TEXT")
            if "is_departed" not in existing:
                conn.execute("ALTER TABLE employees ADD COLUMN is_departed INTEGER DEFAULT 0")
            if "leave_date" not in existing:
                conn.execute("ALTER TABLE employees ADD COLUMN leave_date TEXT")

            # 操作历史表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    target     TEXT NOT NULL,
                    detail     TEXT
                )
                """
            )

    @staticmethod
    def _row_to_employee(row: sqlite3.Row) -> Employee:
        return Employee(
            id=row["id"],
            name=row["name"] or "",
            gender=row["gender"] or "",
            birth_date=row["birth_date"] or "",
            hire_date=row["hire_date"] or "",
            department=row["department"] or "",
            position=row["position"] or "",
            is_cadre=bool(row["is_cadre"]),
            education=row["education"] or "",
            phone=row["phone"] or "",
            email=row["email"] or "",
            contract_end_date=row["contract_end_date"] or "",
            is_departed=bool(row["is_departed"]),
            leave_date=row["leave_date"] or "",
            notes=row["notes"] or "",
        )

    def add(self, e: Employee) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO employees
                   (name, gender, birth_date, hire_date, department, position,
                    is_cadre, education, phone, email, contract_end_date,
                    is_departed, leave_date, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    e.name, e.gender, e.birth_date, e.hire_date,
                    e.department, e.position, int(e.is_cadre),
                    e.education, e.phone, e.email, e.contract_end_date,
                    int(e.is_departed), e.leave_date, e.notes,
                ),
            )
            return int(cur.lastrowid)

    def add_many(self, employees: list[Employee]) -> int:
        """批量导入，返回成功新增条数。"""
        count = 0
        with self._connect() as conn:
            for e in employees:
                cur = conn.execute(
                    """INSERT INTO employees
                       (name, gender, birth_date, hire_date, department, position,
                        is_cadre, education, phone, email, contract_end_date,
                        is_departed, leave_date, notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        e.name, e.gender, e.birth_date, e.hire_date,
                        e.department, e.position, int(e.is_cadre),
                        e.education, e.phone, e.email, e.contract_end_date,
                        int(e.is_departed), e.leave_date, e.notes,
                    ),
                )
                count += 1
        return count

    def update(self, e: Employee) -> None:
        if e.id is None:
            return
        with self._connect() as conn:
            conn.execute(
                """UPDATE employees SET name=?, gender=?, birth_date=?, hire_date=?,
                   department=?, position=?, is_cadre=?, education=?, phone=?, email=?,
                   contract_end_date=?, is_departed=?, leave_date=?, notes=?
                   WHERE id=?""",
                (
                    e.name, e.gender, e.birth_date, e.hire_date,
                    e.department, e.position, int(e.is_cadre),
                    e.education, e.phone, e.email, e.contract_end_date,
                    int(e.is_departed), e.leave_date, e.notes, e.id,
                ),
            )

    def delete(self, employee_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM employees WHERE id=?", (employee_id,))

    def get_all(self) -> list[Employee]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM employees ORDER BY id").fetchall()
        return [self._row_to_employee(r) for r in rows]

    def search(self, keyword: str, department: str = "",
               departed: bool = False) -> list[Employee]:
        """多字段搜索，可叠加部门筛选与在职/离职筛选。

        departed=False 只返回在职员工；True 只返回已离职员工。
        """
        kw = f"%{keyword.strip()}%"
        sql = """SELECT * FROM employees
                 WHERE (name LIKE ? OR department LIKE ? OR position LIKE ?
                        OR phone LIKE ? OR email LIKE ? OR education LIKE ?)
                 AND is_departed = ?"""
        params: list = [kw, kw, kw, kw, kw, kw, int(departed)]
        if department and department != "全部部门":
            sql += " AND department = ?"
            params.append(department)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_employee(r) for r in rows]

    def get_departed(self) -> list[Employee]:
        """返回所有已离职员工。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees WHERE is_departed = 1 ORDER BY id"
            ).fetchall()
        return [self._row_to_employee(r) for r in rows]

    def set_departed(self, employee_id: int, departed: bool,
                     leave_date: str = "") -> None:
        """办理离职 / 恢复在职。"""
        with self._connect() as conn:
            if departed:
                conn.execute(
                    "UPDATE employees SET is_departed=1, leave_date=? WHERE id=?",
                    (leave_date, employee_id),
                )
            else:
                conn.execute(
                    "UPDATE employees SET is_departed=0, leave_date='' WHERE id=?",
                    (employee_id,),
                )

    def get_departments(self) -> list[str]:
        """返回所有不重复的部门名称（按名称排序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT department FROM employees
                   WHERE department IS NOT NULL AND department != ''
                   ORDER BY department"""
            ).fetchall()
        return [r["department"] for r in rows]

    def get_by_department(self, department: str) -> list[Employee]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM employees WHERE department = ? ORDER BY id",
                (department,),
            ).fetchall()
        return [self._row_to_employee(r) for r in rows]

    # ---------- 批量操作 ----------
    def delete_many(self, employee_ids: list[int]) -> int:
        """批量删除，返回实际删除条数。"""
        if not employee_ids:
            return 0
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in employee_ids)
            cur = conn.execute(
                f"DELETE FROM employees WHERE id IN ({placeholders})",
                employee_ids,
            )
            return cur.rowcount

    def set_department_many(self, employee_ids: list[int], department: str) -> int:
        """批量调整部门，返回更新条数。"""
        if not employee_ids:
            return 0
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in employee_ids)
            cur = conn.execute(
                f"UPDATE employees SET department=? WHERE id IN ({placeholders})",
                [department, *employee_ids],
            )
            return cur.rowcount

    # ---------- 操作历史 ----------
    def add_log(self, action: str, target: str, detail: str = "") -> None:
        """记录一次操作。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO operation_log (ts, action, target, detail) VALUES (?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action, target, detail),
            )

    def get_logs(self, limit: int = 300) -> list[dict]:
        """按时间倒序返回操作历史。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operation_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"id": r["id"], "ts": r["ts"], "action": r["action"],
             "target": r["target"], "detail": r["detail"] or ""}
            for r in rows
        ]

    def clear_logs(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM operation_log")
