# -*- coding: utf-8 -*-
"""统计计算模块 —— 基于花名册数据实时汇总各项指标。"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Callable, Iterable

from models import Employee

AGE_BINS: list[tuple[str, Callable[[int], bool]]] = [
    ("25岁以下", lambda a: a < 25),
    ("25-30岁", lambda a: 25 <= a <= 30),
    ("31-35岁", lambda a: 31 <= a <= 35),
    ("36-40岁", lambda a: 36 <= a <= 40),
    ("41-50岁", lambda a: 41 <= a <= 50),
    ("50岁以上", lambda a: a > 50),
]

TENURE_BINS: list[tuple[str, Callable[[float], bool]]] = [
    ("1年以下", lambda t: t < 1),
    ("1-3年", lambda t: 1 <= t < 3),
    ("3-5年", lambda t: 3 <= t < 5),
    ("5-10年", lambda t: 5 <= t < 10),
    ("10年以上", lambda t: t >= 10),
]


def _bin_count(values: Iterable, bins: list[tuple[str, Callable]]) -> dict[str, int]:
    result = {name: 0 for name, _ in bins}
    for value in values:
        for name, predicate in bins:
            if predicate(value):
                result[name] += 1
                break
    return result


def _next_birthday(born: date, ref: date) -> tuple[date, int]:
    """计算下一次生日日期与距今天数（生日当天为 0）。"""
    next_dt = date(ref.year, born.month, born.day)
    if next_dt < ref:
        next_dt = date(ref.year + 1, born.month, born.day)
    return next_dt, (next_dt - ref).days


def compute_birthdays(employees: list[Employee], ref: date | None = None,
                      within_days: int = 30) -> dict:
    """生日统计：本月生日人数 + 未来 N 天内生日提醒列表。

    只统计有合法生日的员工；2 月 29 日在非闰年按 2 月 28 日近似处理。
    """
    ref = ref or date.today()
    month_count = 0
    alerts = []
    for e in employees:
        born = Employee._parse(e.birth_date)
        if born is None:
            continue
        if born.month == ref.month:
            month_count += 1
        # 处理 2 月 29 日在平年的近似
        try:
            next_dt, days = _next_birthday(born, ref)
        except ValueError:
            # 非闰年没有 2 月 29 日，按 2 月 28 日比较
            approx = date(born.year, 2, 28)
            next_dt, days = _next_birthday(approx, ref)
        if days <= within_days:
            age = e.age(ref)
            alerts.append({
                "name": e.name,
                "department": e.department,
                "birth_date": e.birth_date,
                "next_date": next_dt.isoformat(),
                "days": days,
                "age": age + 1 if age is not None and days > 0 else age,
            })
    alerts.sort(key=lambda x: x["days"])
    return {"this_month": month_count, "alerts": alerts, "within_days": within_days}


def compute_stats(employees: list[Employee], ref: date | None = None) -> dict:
    """计算全部统计指标，返回可直接用于 UI 的字典。"""
    ref = ref or date.today()
    total = len(employees)

    gender = Counter(
        e.gender if e.gender in ("男", "女") else "未填写" for e in employees
    )
    cadre_count = sum(1 for e in employees if e.is_cadre)

    ages = [a for e in employees if (a := e.age(ref)) is not None]
    avg_age = round(sum(ages) / len(ages), 1) if ages else 0.0
    age_dist = _bin_count(ages, AGE_BINS)

    tenures = [t for e in employees if (t := e.tenure(ref)) is not None]
    avg_tenure = round(sum(tenures) / len(tenures), 1) if tenures else 0.0
    tenure_dist = _bin_count(tenures, TENURE_BINS)

    dept = Counter(e.department.strip() or "未填写" for e in employees)
    edu = Counter(e.education.strip() or "未填写" for e in employees)

    # 部门员工数：按人数降序
    dept_detail = [
        {"department": name, "count": count}
        for name, count in dept.most_common()
    ]

    # 劳动合同到期统计
    contract = {"expired": 0, "warning": 0, "normal": 0, "none": 0}
    contract_alerts = []
    for e in employees:
        status, remaining = e.contract_status(ref)
        contract[status] += 1
        if status in ("expired", "warning"):
            contract_alerts.append({
                "name": e.name,
                "department": e.department,
                "end_date": e.contract_end_date,
                "status": status,
                "remaining": remaining,
            })
    # 排序：已过期在前，然后按剩余天数升序
    contract_alerts.sort(key=lambda x: (x["status"] != "expired",
                                        x["remaining"] if x["remaining"] is not None else 0))

    # 生日统计
    birthday = compute_birthdays(employees, ref)

    return {
        "total": total,
        "gender": {
            "男": gender.get("男", 0),
            "女": gender.get("女", 0),
            "未填写": gender.get("未填写", 0),
        },
        "cadre_count": cadre_count,
        "cadre_ratio": round(cadre_count / total * 100, 1) if total else 0.0,
        "avg_age": avg_age,
        "age_dist": age_dist,
        "avg_tenure": avg_tenure,
        "tenure_dist": tenure_dist,
        "dept_dist": dict(dept.most_common()),
        "dept_detail": dept_detail,
        "edu_dist": dict(edu.most_common()),
        "contract": contract,
        "contract_alerts": contract_alerts,
        "birthday": birthday,
        "ref_date": ref.isoformat(),
    }
