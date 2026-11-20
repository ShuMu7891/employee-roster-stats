# -*- coding: utf-8 -*-
"""员工花名册统计系统 —— 主程序入口。

功能：录入/导入员工信息 → 自动统计性别、工龄、年龄、干部、部门人数，
并提供劳动合同到期提醒、多字段搜索与部门分类筛选。
UI：iOS Liquid Glass 毛玻璃风格（PySide6 自绘）。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt, QDate, QRectF, QPoint
from PySide6.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QFont, QGuiApplication
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QDialog, QFormLayout, QComboBox, QCheckBox, QDateEdit, QTextEdit,
    QLabel, QMessageBox, QScrollArea, QFrame, QAbstractItemView, QFileDialog,
    QSizePolicy
)

from models import Employee, Database, GENDERS, EDUCATIONS
from stats import compute_stats
from import_utils import parse_file, map_rows, SUPPORTED
from glass_widgets import (
    GlassFrame, GlassButton, NavButton, StatCard, SectionTitle,
    DonutChart, BarChart, hline, COLORS, FONT, _with_alpha, rgba,
    WindowControls, StatusPill
)

APP_TITLE = "员工花名册 · 智能统计"
WARN_DAYS = 30  # 合同到期提前提醒天数


# --------------------------------------------------------------------------- #
# 合同提醒条目
# --------------------------------------------------------------------------- #
class ContractAlertItem(GlassFrame):
    """单条合同到期提醒卡片。"""

    def __init__(self, alert: dict, parent=None):
        super().__init__(parent, radius=16, alpha=165)
        self.setFixedHeight(70)
        expired = alert["status"] == "expired"
        accent = COLORS["pink"] if expired else COLORS["orange"]
        status_text = "已过期" if expired else "即将到期"
        if alert["remaining"] is None:
            days_text = ""
        elif expired:
            days_text = f"已过期 {abs(alert['remaining'])} 天"
        else:
            days_text = f"剩余 {alert['remaining']} 天"

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)

        dot = QLabel("!")
        dot.setFixedSize(34, 34)
        dot.setAlignment(Qt.AlignCenter)
        dot.setFont(QFont(FONT, 16, QFont.Bold))
        dot.setStyleSheet(f"background:{rgba(accent, 40)}; color:{accent}; border-radius:11px;")
        lay.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(f"{alert['name']}　<span style='color:{COLORS['secondary']};font-size:12px;'>{alert['department']}</span>")
        name.setFont(QFont(FONT, 14, QFont.Medium))
        name.setStyleSheet(f"color:{COLORS['ink']};")
        info.addWidget(name)
        sub = QLabel(f"{alert['end_date']} 到期 · {days_text}")
        sub.setFont(QFont(FONT, 12))
        sub.setStyleSheet(f"color:{COLORS['secondary']};")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        badge = QLabel(status_text)
        badge.setFont(QFont(FONT, 12, QFont.Medium))
        badge.setStyleSheet(
            f"background:{rgba(accent, 42)}; color:{accent}; border-radius:9px; padding:4px 10px;"
        )
        lay.addWidget(badge)


# --------------------------------------------------------------------------- #
# 主窗口：自绘渐变壁纸背景
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 860)
        self.setMinimumSize(1080, 720)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._drag_pos = None
        self._maximized = False
        self._normal_geometry = None
        self._build_ui()
        self._bind()
        self.refresh_all()

    # ---------- 背景壁纸 ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor("#E9EEF9"))
        base.setColorAt(0.55, QColor("#F2E9F6"))
        base.setColorAt(1.0, QColor("#E6F0F7"))
        painter.fillRect(self.rect(), base)

        blobs = [
            (0.12, 0.08, 460, QColor(0, 122, 255, 46)),
            (0.90, 0.18, 420, QColor(175, 82, 222, 42)),
            (0.78, 0.92, 500, QColor(255, 45, 85, 34)),
            (0.22, 0.88, 440, QColor(48, 176, 199, 40)),
        ]
        for fx, fy, radius, color in blobs:
            cx, cy = w * fx, h * fy
            g = QRadialGradient(cx, cy, radius)
            g.setColorAt(0, color)
            g.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(g)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        super().paintEvent(event)

    # ---------- 布局 ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # 侧边栏
        self.sidebar = GlassFrame(radius=26, alpha=190)
        self.sidebar.setFixedWidth(228)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(18, 16, 18, 18)
        sb.setSpacing(10)

        # macOS 交通灯窗口控件（左上角）
        self.win_controls = WindowControls()
        self.win_controls.close_btn.clicked.connect(self._on_window_close)
        self.win_controls.min_btn.clicked.connect(self.showMinimized)
        self.win_controls.zoom_btn.clicked.connect(self._toggle_maximize)
        sb.addWidget(self.win_controls)
        sb.addSpacing(14)

        logo = QLabel("花名册")
        logo.setFont(QFont(FONT, 24, QFont.Bold))
        logo.setStyleSheet(f"color:{COLORS['ink']};")
        sb.addWidget(logo)
        sub = QLabel("智能统计 · Liquid Glass")
        sub.setFont(QFont(FONT, 12))
        sub.setStyleSheet(f"color:{COLORS['secondary']};")
        sb.addWidget(sub)
        sb.addSpacing(18)

        self.nav_dash = NavButton("  数据概览", "dashboard")
        self.nav_roster = NavButton("  员工花名册", "roster")
        self.nav_departed = NavButton("  已离职员工", "departed", accent=COLORS["secondary"])
        self.nav_contract = NavButton("  合同到期提醒", "contract")
        self.nav_dash.setChecked(True)
        sb.addWidget(self.nav_dash)
        sb.addWidget(self.nav_roster)
        sb.addWidget(self.nav_departed)
        sb.addWidget(self.nav_contract)
        sb.addStretch(1)

        self.side_count = QLabel("")
        self.side_count.setFont(QFont(FONT, 12))
        self.side_count.setStyleSheet(f"color:{COLORS['secondary']};")
        self.side_count.setWordWrap(True)
        sb.addWidget(self.side_count)

        tip = QLabel("双击表格行可编辑员工信息\n数据保存在本地 employees.db")
        tip.setFont(QFont(FONT, 11))
        tip.setStyleSheet(f"color:{COLORS['secondary']};")
        tip.setWordWrap(True)
        sb.addWidget(tip)
        root.addWidget(self.sidebar)

        # 内容区
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        self.dash_page = self._build_dashboard()
        self.roster_page = self._build_roster()
        self.departed_page = self._build_departed()
        self.contract_page = self._build_contract()
        self.stack.addWidget(self.dash_page)
        self.stack.addWidget(self.roster_page)
        self.stack.addWidget(self.departed_page)
        self.stack.addWidget(self.contract_page)
        root.addWidget(self.stack)

    def _header(self, title: str, subtitle: str) -> QHBoxLayout:
        header = QHBoxLayout()
        header.addWidget(SectionTitle(title, subtitle))
        header.addStretch(1)
        return header

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(14)

        header = self._header("数据概览", "实时统计 · 数据随花名册自动更新")
        self.import_btn_top = GlassButton("导入数据")
        self.add_btn_top = GlassButton("＋ 添加员工", primary=True)
        header.addWidget(self.import_btn_top)
        header.addWidget(self.add_btn_top)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        grid = QVBoxLayout(container)
        grid.setContentsMargins(2, 2, 8, 2)
        grid.setSpacing(14)

        # 统计卡片（9 张，3x3）
        cards = QGridLayout()
        cards.setSpacing(14)
        self.card_total = StatCard("员工总数", "0", "人", COLORS["blue"])
        self.card_male = StatCard("男性员工", "0", "♂", COLORS["teal"])
        self.card_female = StatCard("女性员工", "0", "♀", COLORS["pink"])
        self.card_cadre = StatCard("干部数量", "0", "★", COLORS["orange"])
        self.card_age = StatCard("平均年龄", "0.0", "岁", COLORS["purple"])
        self.card_tenure = StatCard("平均工龄", "0.0", "年", COLORS["green"])
        self.card_dept = StatCard("在职部门数", "0", "部", COLORS["indigo"])
        self.card_warning = StatCard("合同即将到期", "0", "时", COLORS["orange"])
        self.card_expired = StatCard("合同已过期", "0", "!", COLORS["pink"])
        self.card_departed = StatCard("已离职员工", "0", "离", COLORS["secondary"])
        self.all_cards = [
            self.card_total, self.card_male, self.card_female,
            self.card_cadre, self.card_age, self.card_tenure,
            self.card_dept, self.card_warning, self.card_expired,
            self.card_departed,
        ]
        for i, card in enumerate(self.all_cards):
            if i < 9:
                cards.addWidget(card, i // 3, i % 3)
        # 第 10 张「已离职」卡片横跨整行，视觉更均衡
        cards.addWidget(self.card_departed, 3, 0, 1, 3)
        grid.addLayout(cards)

        # 图表行 1：性别 + 部门人数
        charts1 = QHBoxLayout()
        charts1.setSpacing(14)
        gender_frame = GlassFrame(radius=22, alpha=150)
        gf = QVBoxLayout(gender_frame)
        gf.setContentsMargins(18, 16, 18, 16)
        gf.addWidget(SectionTitle("性别分布"))
        self.donut = DonutChart([], "员工")
        gf.addWidget(self.donut)
        charts1.addWidget(gender_frame, 1)

        dept_frame = GlassFrame(radius=22, alpha=150)
        df = QVBoxLayout(dept_frame)
        df.setContentsMargins(18, 16, 18, 16)
        df.addWidget(SectionTitle("各部门员工数"))
        self.bar_dept = BarChart({}, COLORS["blue"])
        df.addWidget(self.bar_dept)
        charts1.addWidget(dept_frame, 1)
        grid.addLayout(charts1)

        # 图表行 2：年龄 + 工龄 + 学历
        charts2 = QHBoxLayout()
        charts2.setSpacing(14)
        for title, color, attr in [
            ("年龄结构", COLORS["purple"], "bar_age"),
            ("工龄结构", COLORS["green"], "bar_tenure"),
            ("学历构成", COLORS["orange"], "bar_edu"),
        ]:
            frame = GlassFrame(radius=22, alpha=150)
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(18, 16, 18, 16)
            fl.addWidget(SectionTitle(title))
            bar = BarChart({}, color)
            setattr(self, attr, bar)
            fl.addWidget(bar)
            charts2.addWidget(frame, 1)
        grid.addLayout(charts2)

        # 合同到期提醒（概览区，最多显示 4 条）
        alert_frame = GlassFrame(radius=22, alpha=150)
        af = QVBoxLayout(alert_frame)
        af.setContentsMargins(18, 16, 18, 16)
        af.setSpacing(10)
        alert_head = QHBoxLayout()
        alert_head.addWidget(SectionTitle("劳动合同到期提醒", f"{WARN_DAYS} 天内到期或已过期"))
        alert_head.addStretch(1)
        more_btn = GlassButton("查看全部")
        more_btn.clicked.connect(lambda: self._switch_page("contract"))
        alert_head.addWidget(more_btn)
        af.addLayout(alert_head)
        self.dash_alert_box = QVBoxLayout()
        self.dash_alert_box.setSpacing(8)
        af.addLayout(self.dash_alert_box)
        grid.addWidget(alert_frame)

        grid.addStretch(1)
        scroll.setWidget(container)
        outer.addWidget(scroll)
        return page

    def _build_roster(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(14)

        # 第一行：标题 + 操作按钮
        header = QHBoxLayout()
        header.addWidget(SectionTitle("员工花名册", "双击行编辑 · 支持搜索与部门筛选"))
        header.addStretch(1)
        self.import_btn = GlassButton("导入")
        self.add_btn = GlassButton("＋ 添加", primary=True)
        self.edit_btn = GlassButton("编辑")
        self.depart_btn = GlassButton("办理离职", accent=COLORS["orange"])
        self.del_btn = GlassButton("删除")
        for btn in (self.import_btn, self.add_btn, self.edit_btn, self.depart_btn, self.del_btn):
            header.addWidget(btn)
        lay.addLayout(header)

        # 第二行：筛选控件 + 计数
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.dept_filter = QComboBox()
        self.dept_filter.setFixedHeight(40)
        self.dept_filter.setFixedWidth(150)
        self.dept_filter.setStyleSheet(f"""
            QComboBox {{ background:rgba(255,255,255,0.6);
            border:1px solid rgba(255,255,255,0.85); border-radius:13px;
            padding:0 12px; color:{COLORS['ink']}; font-size:14px; font-family:{FONT}; }}
        """)
        filter_row.addWidget(self.dept_filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 搜索姓名 / 部门 / 职位 / 电话 / 学历")
        self.search.setFixedHeight(40)
        self.search.setMinimumWidth(280)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,0.6);
                border: 1px solid rgba(255,255,255,0.85);
                border-radius: 13px; padding: 0 14px;
                color: {COLORS['ink']}; font-size: 14px;
                font-family: {FONT};
            }}
        """)
        filter_row.addWidget(self.search, 1)
        self.count_label = QLabel("")
        self.count_label.setFont(QFont(FONT, 12))
        self.count_label.setStyleSheet(f"color:{COLORS['secondary']};")
        filter_row.addWidget(self.count_label)
        lay.addLayout(filter_row)

        table_frame = GlassFrame(radius=22, alpha=160)
        tf = QVBoxLayout(table_frame)
        tf.setContentsMargins(14, 14, 14, 14)

        self.table = QTableWidget()
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels([
            "ID", "姓名", "性别", "年龄", "工龄", "部门", "职位",
            "干部", "学历", "电话", "入职日期", "合同到期", "状态",
        ])
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none;
                color: {COLORS['ink']}; font-size: 13px; font-family: {FONT};
                gridline-color: rgba(120,120,128,0.12);
            }}
            QHeaderView::section {{
                background: rgba(255,255,255,0.5); color: {COLORS['ink']};
                font-weight: bold; font-size: 13px; border: none;
                border-bottom: 1px solid rgba(120,120,128,0.2); padding: 8px 4px;
            }}
            QTableWidget::item {{ padding: 6px 4px; }}
            QTableWidget::item:selected {{ background: rgba(0,122,255,0.22); }}
        """)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(10, QHeaderView.Fixed)
        hh.setSectionResizeMode(11, QHeaderView.Fixed)
        hh.setSectionResizeMode(12, QHeaderView.Fixed)
        self.table.setColumnWidth(10, 108)
        self.table.setColumnWidth(11, 108)
        self.table.setColumnWidth(12, 72)
        hh.setStretchLastSection(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._on_edit)
        tf.addWidget(self.table)
        lay.addWidget(table_frame, 1)
        return page

    def _build_departed(self) -> QWidget:
        """已离职员工列表页。"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(SectionTitle("已离职员工", "离职人员档案 · 可恢复在职"))
        header.addStretch(1)
        self.depart_count_label = QLabel("")
        self.depart_count_label.setFont(QFont(FONT, 13, QFont.Medium))
        self.depart_count_label.setStyleSheet(f"color:{COLORS['secondary']};")
        header.addWidget(self.depart_count_label)
        self.restore_btn = GlassButton("恢复在职", accent=COLORS["green"])
        header.addWidget(self.restore_btn)
        lay.addLayout(header)

        table_frame = GlassFrame(radius=22, alpha=160)
        tf = QVBoxLayout(table_frame)
        tf.setContentsMargins(14, 14, 14, 14)

        self.depart_table = QTableWidget()
        self.depart_table.setColumnCount(6)
        self.depart_table.setHorizontalHeaderLabels([
            "ID", "姓名", "性别", "部门", "职位", "离职日期",
        ])
        self.depart_table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none;
                color: {COLORS['ink']}; font-size: 13px; font-family: {FONT};
                gridline-color: rgba(120,120,128,0.12);
            }}
            QHeaderView::section {{
                background: rgba(255,255,255,0.5); color: {COLORS['ink']};
                font-weight: bold; font-size: 13px; border: none;
                border-bottom: 1px solid rgba(120,120,128,0.2); padding: 8px 4px;
            }}
            QTableWidget::item {{ padding: 6px 4px; }}
            QTableWidget::item:selected {{ background: rgba(0,122,255,0.22); }}
        """)
        self.depart_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.depart_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.depart_table.verticalHeader().setVisible(False)
        self.depart_table.setShowGrid(True)
        dhh = self.depart_table.horizontalHeader()
        dhh.setSectionResizeMode(QHeaderView.ResizeToContents)
        dhh.setSectionResizeMode(5, QHeaderView.Fixed)
        self.depart_table.setColumnWidth(5, 120)
        dhh.setStretchLastSection(False)
        self.depart_table.verticalHeader().setDefaultSectionSize(38)
        tf.addWidget(self.depart_table)
        lay.addWidget(table_frame, 1)
        return page

    def _build_contract(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(14)

        header = self._header("劳动合同到期提醒", "已过期与即将到期的合同一览")
        warn_btn = GlassButton("⚠ 提前 30 天提醒")
        warn_btn.setEnabled(False)
        header.addWidget(warn_btn)
        lay.addLayout(header)

        self.contract_summary = QLabel("")
        self.contract_summary.setFont(QFont(FONT, 14, QFont.Medium))
        self.contract_summary.setStyleSheet(f"color:{COLORS['ink']};")
        lay.addWidget(self.contract_summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        container = QWidget()
        container.setStyleSheet("background:transparent;")
        self.contract_box = QVBoxLayout(container)
        self.contract_box.setContentsMargins(2, 2, 8, 2)
        self.contract_box.setSpacing(10)
        self.contract_box.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        lay.addWidget(scroll, 1)
        return page

    # ---------- 信号绑定 ----------
    def _bind(self):
        for nav in (self.nav_dash, self.nav_roster, self.nav_departed, self.nav_contract):
            nav.checkedSignal.connect(self._switch_page)
        self.add_btn.clicked.connect(self._on_add)
        self.add_btn_top.clicked.connect(self._on_add)
        self.import_btn.clicked.connect(self._on_import)
        self.import_btn_top.clicked.connect(self._on_import)
        self.edit_btn.clicked.connect(self._on_edit)
        self.depart_btn.clicked.connect(self._on_depart)
        self.restore_btn.clicked.connect(self._on_restore)
        self.del_btn.clicked.connect(self._on_delete)
        self.search.textChanged.connect(self._on_search)
        self.dept_filter.currentTextChanged.connect(self._on_search)

    def _switch_page(self, key: str):
        for nav in (self.nav_dash, self.nav_roster, self.nav_departed, self.nav_contract):
            nav.setChecked(nav.key == key)
        pages = {"dashboard": self.dash_page, "roster": self.roster_page,
                 "departed": self.departed_page, "contract": self.contract_page}
        self.stack.setCurrentWidget(pages[key])
        if key == "dashboard":
            self.refresh_dashboard()
        elif key == "roster":
            self.refresh_table()
        elif key == "departed":
            self.refresh_departed()
        else:
            self.refresh_contract()

    # ---------- 数据刷新 ----------
    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_table()
        self.refresh_departed()
        self.refresh_contract()
        self._refresh_dept_filter()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh_dashboard(self):
        # 统计口径：在职员工；离职人员单独统计
        active = [e for e in self.db.get_all() if not e.is_departed]
        departed_count = len(self.db.get_departed())
        stats = compute_stats(active)
        self.card_total.set_value(stats["total"])
        self.card_male.set_value(stats["gender"]["男"])
        self.card_female.set_value(stats["gender"]["女"])
        self.card_cadre.set_value(stats["cadre_count"])
        self.card_age.set_value(f"{stats['avg_age']:.1f}")
        self.card_tenure.set_value(f"{stats['avg_tenure']:.1f}")
        self.card_dept.set_value(len(stats["dept_detail"]))
        self.card_warning.set_value(stats["contract"]["warning"])
        self.card_expired.set_value(stats["contract"]["expired"])
        self.card_departed.set_value(departed_count)

        self.donut.set_data([
            ("男", stats["gender"]["男"], COLORS["teal"]),
            ("女", stats["gender"]["女"], COLORS["pink"]),
        ], "员工")
        self.bar_dept.set_data(stats["dept_dist"], COLORS["blue"])
        self.bar_age.set_data(stats["age_dist"], COLORS["purple"])
        self.bar_tenure.set_data(stats["tenure_dist"], COLORS["green"])
        self.bar_edu.set_data(stats["edu_dist"], COLORS["orange"])

        # 概览提醒条目（最多 4 条）
        self._clear_layout(self.dash_alert_box)
        alerts = stats["contract_alerts"][:4]
        if alerts:
            for alert in alerts:
                self.dash_alert_box.addWidget(ContractAlertItem(alert))
        else:
            empty = QLabel("暂无到期提醒，所有合同状态正常 ✓")
            empty.setFont(QFont(FONT, 13))
            empty.setStyleSheet(f"color:{COLORS['secondary']}; padding:14px;")
            self.dash_alert_box.addWidget(empty)

        c = stats["contract"]
        self.side_count.setText(
            f"在职 {stats['total']} 人 · 已离职 {departed_count} 人\n"
            f"部门 {len(stats['dept_detail'])} 个 · 合同提醒 {c['expired'] + c['warning']} 条"
        )

    def refresh_contract(self):
        active = [e for e in self.db.get_all() if not e.is_departed]
        stats = compute_stats(active)
        c = stats["contract"]
        self.contract_summary.setText(
            f"共 {stats['total']} 份合同　·　已过期 {c['expired']} 份　·　"
            f"{WARN_DAYS} 天内到期 {c['warning']} 份　·　正常 {c['normal']} 份"
        )
        self._clear_layout(self.contract_box)
        alerts = stats["contract_alerts"]
        if alerts:
            for alert in alerts:
                self.contract_box.addWidget(ContractAlertItem(alert))
            self.contract_box.addStretch(1)
        else:
            empty = GlassFrame(radius=20, alpha=150)
            el = QVBoxLayout(empty)
            label = QLabel("🎉 暂无合同到期提醒\n所有合同均在有效期内")
            label.setFont(QFont(FONT, 16))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color:{COLORS['secondary']}; padding:40px;")
            el.addWidget(label)
            self.contract_box.addWidget(empty)

    def refresh_departed(self):
        """刷新已离职员工列表。"""
        departed = self.db.get_departed()
        self.depart_count_label.setText(f"共 {len(departed)} 人")
        self.depart_table.setRowCount(len(departed))
        for r, e in enumerate(departed):
            values = [
                str(e.id), e.name, e.gender,
                e.department, e.position,
                e.leave_date or "-",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignVCenter | Qt.AlignLeft if c == 1
                    else Qt.AlignVCenter | Qt.AlignCenter
                )
                if c == 5:
                    item.setForeground(QColor(COLORS["secondary"]))
                self.depart_table.setItem(r, c, item)

    def _refresh_dept_filter(self):
        current = self.dept_filter.currentText()
        departments = self.db.get_departments()
        self.dept_filter.blockSignals(True)
        self.dept_filter.clear()
        self.dept_filter.addItem("全部部门")
        self.dept_filter.addItems(departments)
        idx = self.dept_filter.findText(current)
        self.dept_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.dept_filter.blockSignals(False)

    def refresh_table(self):
        keyword = self.search.text().strip()
        department = self.dept_filter.currentText()
        employees = self.db.search(keyword, department, departed=False)
        active_total = sum(1 for e in self.db.get_all() if not e.is_departed)
        self.table.setRowCount(len(employees))
        self.count_label.setText(f"在职 {len(employees)} / {active_total} 人")
        ref = date.today()
        for r, e in enumerate(employees):
            age = e.age(ref)
            tenure = e.tenure(ref)
            status, remaining = e.contract_status(ref, WARN_DAYS)
            if status == "expired":
                contract_text = f"已过期{abs(remaining)}天"
                contract_color = COLORS["pink"]
            elif status == "warning":
                contract_text = f"{remaining}天后到期"
                contract_color = COLORS["orange"]
            elif status == "none":
                contract_text = "-"
                contract_color = COLORS["secondary"]
            else:
                contract_text = e.contract_end_date
                contract_color = COLORS["ink"]
            values = [
                str(e.id), e.name, e.gender,
                str(age) if age is not None else "-",
                f"{tenure:.1f}" if tenure is not None else "-",
                e.department, e.position,
                "是" if e.is_cadre else "否",
                e.education, e.phone, e.hire_date, contract_text,
                "在职",
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignVCenter | Qt.AlignLeft if c == 1
                    else Qt.AlignVCenter | Qt.AlignCenter
                )
                if c == 11:
                    item.setForeground(QColor(contract_color))
                elif c == 12:
                    item.setForeground(QColor(COLORS["green"]))
                    item.setFont(QFont(FONT, 12, QFont.Medium))
                self.table.setItem(r, c, item)

    def _on_search(self, _=None):
        self.refresh_table()

    # ---------- 增删改 ----------
    def _current_employee(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        emp_id = int(self.table.item(row, 0).text())
        return next((e for e in self.db.get_all() if e.id == emp_id), None)

    def _on_add(self):
        dialog = EmployeeDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.db.add(dialog.employee())
            self.refresh_all()
            self._toast("已添加员工，统计已自动更新")

    def _on_edit(self):
        emp = self._current_employee()
        if not emp:
            QMessageBox.information(self, "提示", "请先选中一行员工")
            return
        dialog = EmployeeDialog(self, emp)
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.employee()
            updated.id = emp.id
            self.db.update(updated)
            self.refresh_all()
            self._toast("已更新员工信息")

    def _on_delete(self):
        emp = self._current_employee()
        if not emp:
            QMessageBox.information(self, "提示", "请先选中一行员工")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除员工「{emp.name}」吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete(emp.id)
            self.refresh_all()
            self._toast("已删除员工")

    def _on_depart(self):
        """把选中的在职员工标记为离职，并登记离职日期。"""
        emp = self._current_employee()
        if not emp:
            QMessageBox.information(self, "提示", "请先在花名册中选中一行员工")
            return
        reply = QMessageBox.question(
            self, "办理离职",
            f"确定将「{emp.name}」标记为已离职吗？\n该员工将移入「已离职员工」列表。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        dialog = DepartDateDialog(self, emp.name)
        if dialog.exec() == QDialog.Accepted:
            self.db.set_departed(emp.id, True, dialog.leave_date())
            self.refresh_all()
            self._toast(f"已办理 {emp.name} 的离职手续")

    def _on_restore(self):
        """把选中的离职员工恢复为在职。"""
        row = self.depart_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在已离职列表中选中一行")
            return
        emp_id = int(self.depart_table.item(row, 0).text())
        emp = next((e for e in self.db.get_departed() if e.id == emp_id), None)
        if not emp:
            return
        reply = QMessageBox.question(
            self, "恢复在职",
            f"确定将「{emp.name}」恢复为在职员工吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.set_departed(emp.id, False)
            self.refresh_all()
            self._toast(f"已将 {emp.name} 恢复为在职")

    def _on_import(self):
        dialog = ImportDialog(self, self.db)
        if dialog.exec() == QDialog.Accepted and dialog.imported_count:
            self.refresh_all()
            self._toast(f"成功导入 {dialog.imported_count} 名员工")

    def _toast(self, message: str):
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(message, 4000)

    # ---------- macOS 窗口控制 ----------
    def _on_window_close(self):
        self.close()

    def _toggle_maximize(self):
        """全屏 / 窗口化切换（macOS 绿色按钮）。"""
        if self._maximized:
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self._maximized = False
        else:
            self._normal_geometry = self.geometry()
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.setGeometry(screen)
            self._maximized = True

    # ---------- 无边框窗口拖动 ----------
    def mousePressEvent(self, event):
        # 顶部区域（y<52，x>90 避开交通灯）可拖动窗口
        if (event.button() == Qt.LeftButton and event.position().y() < 52
                and event.position().x() > 90):
            if self._maximized:
                # 从最大化拖动：按光标在屏幕上的相对位置还原窗口
                ratio = event.globalPosition().x() / max(1, self.width())
                self._toggle_maximize()
                nx = int(self._normal_geometry.width() * ratio)
                self._drag_pos = QPoint(nx, 16)
                self.move(event.globalPosition().toPoint() - self._drag_pos)
            else:
                self._drag_pos = (event.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())
            event.accept()
        else:
            self._drag_pos = None
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        # 双击顶部标题区切换最大化（macOS 行为）
        if event.position().y() < 52 and event.position().x() > 90:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# --------------------------------------------------------------------------- #
# 员工编辑对话框
# --------------------------------------------------------------------------- #
class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee: Employee = None):
        super().__init__(parent)
        self.employee_data = employee
        self.setWindowTitle("编辑员工信息" if employee else "添加员工")
        self.setModal(True)
        self.setFixedWidth(480)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        bg = GlassFrame(radius=24, alpha=225)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(bg)
        inner = QVBoxLayout(bg)
        inner.setContentsMargins(28, 26, 28, 24)
        inner.setSpacing(14)

        title = QLabel("编辑员工信息" if employee else "添加新员工")
        title.setFont(QFont(FONT, 22, QFont.Bold))
        title.setStyleSheet(f"color:{COLORS['ink']};")
        inner.addWidget(title)
        inner.addWidget(hline())

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.name = QLineEdit()
        self.gender = QComboBox()
        self.gender.addItems(list(GENDERS))
        self.birth = QDateEdit()
        self.birth.setCalendarPopup(True)
        self.birth.setDisplayFormat("yyyy-MM-dd")
        self.birth.setDate(QDate(1995, 1, 1))
        self.hire = QDateEdit()
        self.hire.setCalendarPopup(True)
        self.hire.setDisplayFormat("yyyy-MM-dd")
        self.hire.setDate(QDate.currentDate())
        self.dept = QLineEdit()
        self.position = QLineEdit()
        self.cadre = QCheckBox("是 / 否")
        self.edu = QComboBox()
        self.edu.addItems(list(EDUCATIONS))
        self.edu.setCurrentText("本科")
        self.phone = QLineEdit()
        self.email = QLineEdit()
        self.contract_end = QDateEdit()
        self.contract_end.setCalendarPopup(True)
        self.contract_end.setDisplayFormat("yyyy-MM-dd")
        self.contract_end.setDate(QDate.currentDate().addYears(1))
        self.contract_none = QCheckBox("未填写")
        self.contract_none.setChecked(not (employee and employee.contract_end_date))
        self.contract_none.toggled.connect(self.contract_end.setDisabled)
        self.contract_end.setDisabled(self.contract_none.isChecked())
        self.notes = QTextEdit()
        self.notes.setFixedHeight(56)

        inputs = [self.name, self.gender, self.birth, self.hire, self.dept,
                  self.position, self.cadre, self.edu, self.phone, self.email, self.notes]
        for w in inputs:
            if isinstance(w, QLineEdit):
                w.setFixedHeight(34)
                w.setStyleSheet(f"""
                    QLineEdit {{ background:rgba(255,255,255,0.7);
                    border:1px solid rgba(255,255,255,0.9); border-radius:9px;
                    padding:0 10px; font-size:13px; font-family:{FONT}; }}
                """)
            elif isinstance(w, QComboBox):
                w.setFixedHeight(34)
                w.setStyleSheet(f"""
                    QComboBox {{ background:rgba(255,255,255,0.7);
                    border:1px solid rgba(255,255,255,0.9); border-radius:9px;
                    padding:0 8px; font-size:13px; font-family:{FONT}; }}
                """)
            elif isinstance(w, QDateEdit):
                w.setFixedHeight(34)
                w.setStyleSheet(f"""
                    QDateEdit {{ background:rgba(255,255,255,0.7);
                    border:1px solid rgba(255,255,255,0.9); border-radius:9px;
                    padding:0 8px; font-size:13px; font-family:{FONT}; }}
                """)
            elif isinstance(w, QTextEdit):
                w.setStyleSheet(f"""
                    QTextEdit {{ background:rgba(255,255,255,0.7);
                    border:1px solid rgba(255,255,255,0.9); border-radius:9px;
                    padding:6px; font-size:13px; font-family:{FONT}; }}
                """)

        form.addRow("姓名 *", self.name)
        form.addRow("性别", self.gender)
        form.addRow("出生日期", self.birth)
        form.addRow("入职日期", self.hire)
        form.addRow("部门", self.dept)
        form.addRow("职位", self.position)
        form.addRow("是否干部", self.cadre)
        form.addRow("学历", self.edu)
        form.addRow("电话", self.phone)
        form.addRow("邮箱", self.email)
        contract_row = QHBoxLayout()
        contract_row.addWidget(self.contract_end)
        contract_row.addWidget(self.contract_none)
        form.addRow("合同到期日", contract_row)

        # 离职状态：勾选后填写离职日期
        self.departed = QCheckBox("已离职")
        self.leave = QDateEdit()
        self.leave.setCalendarPopup(True)
        self.leave.setDisplayFormat("yyyy-MM-dd")
        self.leave.setDate(QDate.currentDate())
        self.leave.setFixedHeight(34)
        self.leave.setStyleSheet(f"""
            QDateEdit {{ background:rgba(255,255,255,0.7);
            border:1px solid rgba(255,255,255,0.9); border-radius:9px;
            padding:0 8px; font-size:13px; font-family:{FONT}; }}
        """)
        self.departed.toggled.connect(self.leave.setEnabled)
        leave_row = QHBoxLayout()
        leave_row.addWidget(self.departed)
        leave_row.addWidget(self.leave)
        leave_row.addStretch(1)
        form.addRow("离职状态", leave_row)

        form.addRow("备注", self.notes)
        inner.addLayout(form)

        if employee:
            self.name.setText(employee.name)
            if employee.gender in GENDERS:
                self.gender.setCurrentText(employee.gender)
            self._set_date(self.birth, employee.birth_date)
            self._set_date(self.hire, employee.hire_date)
            self.dept.setText(employee.department)
            self.position.setText(employee.position)
            self.cadre.setChecked(employee.is_cadre)
            if employee.education in EDUCATIONS:
                self.edu.setCurrentText(employee.education)
            self.phone.setText(employee.phone)
            self.email.setText(employee.email)
            self.contract_none.setChecked(not employee.contract_end_date)
            if employee.contract_end_date:
                self._set_date(self.contract_end, employee.contract_end_date)
            self.departed.setChecked(employee.is_departed)
            self.leave.setEnabled(employee.is_departed)
            if employee.leave_date:
                self._set_date(self.leave, employee.leave_date)
            self.notes.setPlainText(employee.notes)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = GlassButton("取消")
        ok = GlassButton("保存", primary=True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_ok)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        inner.addLayout(buttons)

    @staticmethod
    def _set_date(edit: QDateEdit, text: str):
        if text:
            try:
                y, m, d = map(int, text.split("-"))
                edit.setDate(QDate(y, m, d))
            except (ValueError, TypeError):
                pass

    def _on_ok(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "提示", "请填写姓名")
            return
        self.accept()

    def employee(self) -> Employee:
        contract = "" if self.contract_none.isChecked() else self.contract_end.date().toString("yyyy-MM-dd")
        departed = self.departed.isChecked()
        leave_date = self.leave.date().toString("yyyy-MM-dd") if departed else ""
        return Employee(
            name=self.name.text().strip(),
            gender=self.gender.currentText(),
            birth_date=self.birth.date().toString("yyyy-MM-dd"),
            hire_date=self.hire.date().toString("yyyy-MM-dd"),
            department=self.dept.text().strip(),
            position=self.position.text().strip(),
            is_cadre=self.cadre.isChecked(),
            education=self.edu.currentText(),
            phone=self.phone.text().strip(),
            email=self.email.text().strip(),
            contract_end_date=contract,
            is_departed=departed,
            leave_date=leave_date,
            notes=self.notes.toPlainText().strip(),
        )

    def mousePressEvent(self, event):
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag") and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)


# --------------------------------------------------------------------------- #
# 离职日期对话框
# --------------------------------------------------------------------------- #
class DepartDateDialog(QDialog):
    """办理离职时选择离职日期。"""

    def __init__(self, parent=None, name: str = ""):
        super().__init__(parent)
        self.setModal(True)
        self.setFixedWidth(360)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        bg = GlassFrame(radius=24, alpha=230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(bg)
        inner = QVBoxLayout(bg)
        inner.setContentsMargins(26, 24, 26, 22)
        inner.setSpacing(16)

        title = QLabel("办理离职")
        title.setFont(QFont(FONT, 20, QFont.Bold))
        title.setStyleSheet(f"color:{COLORS['ink']};")
        inner.addWidget(title)
        tip = QLabel(f"为「{name}」选择离职日期")
        tip.setFont(QFont(FONT, 13))
        tip.setStyleSheet(f"color:{COLORS['secondary']};")
        inner.addWidget(tip)

        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setDate(QDate.currentDate())
        self.date.setFixedHeight(38)
        self.date.setStyleSheet(f"""
            QDateEdit {{ background:rgba(255,255,255,0.75);
            border:1px solid rgba(255,255,255,0.9); border-radius:10px;
            padding:0 10px; font-size:14px; font-family:{FONT}; }}
        """)
        inner.addWidget(self.date)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = GlassButton("取消")
        ok = GlassButton("确认离职", primary=True, accent=COLORS["orange"])
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        inner.addLayout(buttons)

    def leave_date(self) -> str:
        return self.date.date().toString("yyyy-MM-dd")

    def mousePressEvent(self, event):
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag") and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)


# --------------------------------------------------------------------------- #
# 导入对话框
# --------------------------------------------------------------------------- #
class ImportDialog(QDialog):
    """文件导入：选择文件 → 解析预览 → 字段映射提示 → 确认导入。"""

    def __init__(self, parent=None, db: Database = None):
        super().__init__(parent)
        self.db = db
        self.imported_count = 0
        self.records: list[dict] = []
        self.setWindowTitle("导入员工数据")
        self.setModal(True)
        self.resize(760, 620)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        bg = GlassFrame(radius=24, alpha=230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(bg)
        inner = QVBoxLayout(bg)
        inner.setContentsMargins(26, 24, 26, 22)
        inner.setSpacing(12)

        title = QLabel("导入员工数据")
        title.setFont(QFont(FONT, 22, QFont.Bold))
        title.setStyleSheet(f"color:{COLORS['ink']};")
        inner.addWidget(title)
        hint = QLabel("支持 xlsx / xls / csv / pdf / pptx / ppt，自动识别常见中英文表头")
        hint.setFont(QFont(FONT, 12))
        hint.setStyleSheet(f"color:{COLORS['secondary']};")
        inner.addWidget(hint)

        # 选择文件行
        file_row = QHBoxLayout()
        self.file_label = QLabel("尚未选择文件")
        self.file_label.setFont(QFont(FONT, 13))
        self.file_label.setStyleSheet(f"color:{COLORS['secondary']};")
        choose_btn = GlassButton("选择文件")
        choose_btn.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(choose_btn)
        inner.addLayout(file_row)

        self.map_label = QLabel("")
        self.map_label.setFont(QFont(FONT, 12))
        self.map_label.setStyleSheet(f"color:{COLORS['secondary']};")
        self.map_label.setWordWrap(True)
        inner.addWidget(self.map_label)

        self.preview = QTableWidget()
        self.preview.setStyleSheet(f"""
            QTableWidget {{ background:rgba(255,255,255,0.45); border:none;
                color:{COLORS['ink']}; font-size:12px; font-family:{FONT};
                gridline-color:rgba(120,120,128,0.12); border-radius:12px; }}
            QHeaderView::section {{ background:rgba(255,255,255,0.6);
                font-weight:bold; border:none; padding:6px; }}
        """)
        self.preview.verticalHeader().setVisible(False)
        inner.addWidget(self.preview, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = GlassButton("取消")
        self.ok_btn = GlassButton("确认导入", primary=True)
        self.ok_btn.setEnabled(False)
        cancel.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self._on_import)
        buttons.addWidget(cancel)
        buttons.addWidget(self.ok_btn)
        inner.addLayout(buttons)

    def _choose_file(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED))
        path, _ = QFileDialog.getOpenFileName(
            self, "选择员工数据文件", "", f"数据文件 ({exts});;所有文件 (*)"
        )
        if not path:
            return
        self.file_label.setText(Path(path).name)
        try:
            headers, rows, fmt = parse_file(path)
            records, unknown = map_rows(headers, rows)
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            self.records = []
            self.ok_btn.setEnabled(False)
            return

        self.records = records
        self._build_preview(records)
        recognized = sorted({k for rec in records for k in rec})
        field_names = {
            "name": "姓名", "gender": "性别", "birth_date": "出生日期",
            "hire_date": "入职日期", "department": "部门", "position": "职位",
            "is_cadre": "干部", "education": "学历", "phone": "电话",
            "email": "邮箱", "contract_end_date": "合同到期", "notes": "备注",
        }
        rec_text = "、".join(field_names.get(f, f) for f in recognized)
        msg = f"解析到 {len(records)} 条有效记录（{fmt.upper()}），识别字段：{rec_text}"
        if unknown:
            msg += f"\n未识别列（已忽略）：{'、'.join(unknown)}"
        self.map_label.setText(msg)
        self.ok_btn.setEnabled(len(records) > 0)

    def _build_preview(self, records: list[dict]):
        columns = [
            ("name", "姓名"), ("gender", "性别"), ("department", "部门"),
            ("position", "职位"), ("education", "学历"), ("phone", "电话"),
            ("hire_date", "入职日期"), ("contract_end_date", "合同到期"),
        ]
        self.preview.setColumnCount(len(columns))
        self.preview.setHorizontalHeaderLabels([c[1] for c in columns])
        self.preview.setRowCount(min(len(records), 100))
        for r, rec in enumerate(records[:100]):
            for c, (key, _) in enumerate(columns):
                self.preview.setItem(r, c, QTableWidgetItem(str(rec.get(key, ""))))
        hh = self.preview.horizontalHeader()
        for c in range(len(columns)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)

    def _on_import(self):
        if not self.records:
            return
        employees = [Employee(**rec) for rec in self.records]
        self.imported_count = self.db.add_many(employees)
        self.accept()

    def mousePressEvent(self, event):
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag") and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont(FONT, 13))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
