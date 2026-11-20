# -*- coding: utf-8 -*-
"""Liquid Glass 风格 UI 组件库（PySide6 实现）。

设计要点（对齐 Apple Liquid Glass / HIG）：
- 半透明玻璃填充 + 顶部高光边框 + 柔和投影，模拟光线打在玻璃上
- 统计卡片 hover 时提亮（interactive），按下有反馈
- 语义化系统色：蓝 #007AFF / 绿 #34C759 / 橙 #FF9500 / 粉 #FF2D55 / 紫 #AF52DE
- 字号按 Dynamic Type：Large Title 34 / Headline 17 / Body 15 / Caption 12
"""
from __future__ import annotations

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QLineF, QPropertyAnimation, QEasingCurve, Property, Signal
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QLinearGradient, QRadialGradient, QFont
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QSizePolicy
)

FONT = "'PingFang SC','Microsoft YaHei','Helvetica Neue',sans-serif"

COLORS = {
    "blue": "#007AFF",
    "green": "#34C759",
    "orange": "#FF9500",
    "pink": "#FF2D55",
    "purple": "#AF52DE",
    "teal": "#30B0C7",
    "indigo": "#5856D6",
    "ink": "#1C1C1E",
    "secondary": "#6E6E73",
}


def _with_alpha(hex_color: str, alpha: int) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def rgba(hex_color: str, alpha: int) -> str:
    """把 #RRGGBB 转成 Qt 样式表安全的 rgba(r,g,b,a) 字符串。

    注意：不要用 `#RRGGBBAA` 拼在样式表里，Qt 会按 #AARRGGBB 解析导致颜色错乱。
    """
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


# --------------------------------------------------------------------------- #
# 玻璃容器
# --------------------------------------------------------------------------- #
class GlassFrame(QFrame):
    """通用玻璃面板：半透明渐变填充 + 高光边框 + 柔和投影。"""

    def __init__(self, parent=None, radius: int = 22, alpha: int = 150,
                 tint: str = "#FFFFFF"):
        super().__init__(parent)
        self.radius = radius
        self.tint = QColor(tint)
        self._alpha = alpha
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(24, 34, 64, 40))
        self.setGraphicsEffect(shadow)

    def getAlpha(self) -> int:
        return self._alpha

    def setAlpha(self, value) -> None:
        self._alpha = int(value)
        self.update()

    glassAlpha = Property(int, getAlpha, setAlpha)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        # 玻璃主体：斜向渐变，左上更亮
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0, QColor(self.tint.red(), self.tint.green(),
                                  self.tint.blue(), self._alpha))
        fill.setColorAt(1, QColor(self.tint.red(), self.tint.green(),
                                  self.tint.blue(), int(self._alpha * 0.72)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, self.radius, self.radius)

        # 镜面高光：顶部一片柔和的白色反光，模拟 iOS 玻璃上缘的光泽
        sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + rect.height() * 0.42))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 105))
        sheen.setColorAt(0.5, QColor(255, 255, 255, 24))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(sheen)
        painter.drawRoundedRect(rect, self.radius, self.radius)

        # 底部冷色反光：极淡的蓝紫，模拟背景光透过玻璃底部
        bounce = QLinearGradient(QPointF(rect.left(), rect.bottom() - rect.height() * 0.3), rect.bottomLeft())
        bounce.setColorAt(0.0, QColor(120, 160, 255, 0))
        bounce.setColorAt(1.0, QColor(140, 130, 230, 26))
        painter.setBrush(bounce)
        painter.drawRoundedRect(rect, self.radius, self.radius)

        # 高光边框：左侧亮、底部弱，模拟光线落在材质上
        border = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        border.setColorAt(0.0, QColor(255, 255, 255, 235))
        border.setColorAt(0.5, QColor(255, 255, 255, 90))
        border.setColorAt(1.0, QColor(255, 255, 255, 150))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(border, 1.2))
        painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6),
                                self.radius, self.radius)
        super().paintEvent(event)


# --------------------------------------------------------------------------- #
# 统计数字卡片
# --------------------------------------------------------------------------- #
class StatCard(GlassFrame):
    """统计卡片：图标 + 大数字 + 标题，hover 提亮、press 收缩。"""

    def __init__(self, title: str, value, icon: str = "", accent: str = COLORS["blue"],
                 parent=None):
        super().__init__(parent, radius=20, alpha=150)
        self.accent = accent
        self.setFixedHeight(128)
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 10)
        lay.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.icon = QLabel(icon)
        self.icon.setFixedSize(30, 30)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFont(QFont(FONT, 14, QFont.Bold))
        self.icon.setStyleSheet(
            f"background:{rgba(accent, 42)}; color:{accent}; border-radius:9px;"
        )
        head.addWidget(self.icon)
        head.addStretch(1)
        lay.addLayout(head)

        self.value = QLabel(str(value))
        self.value.setFont(QFont(FONT, 30, QFont.Bold))
        self.value.setStyleSheet(f"color:{accent}; padding:0px;")
        lay.addWidget(self.value)

        self.title = QLabel(title)
        self.title.setFont(QFont(FONT, 13))
        self.title.setStyleSheet(f"color:{COLORS['secondary']}; padding:0px;")
        lay.addWidget(self.title)

        self._anim = QPropertyAnimation(self, b"glassAlpha", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_value(self, value) -> None:
        self.value.setText(str(value))

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self.glassAlpha)
        self._anim.setEndValue(205)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self.glassAlpha)
        self._anim.setEndValue(150)
        self._anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.setAlpha(235)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setAlpha(205 if self.underMouse() else 150)
        super().mouseReleaseEvent(event)


# --------------------------------------------------------------------------- #
# 按钮
# --------------------------------------------------------------------------- #
class GlassButton(QPushButton):
    def __init__(self, text: str, parent=None, accent: str = COLORS["blue"],
                 primary: bool = False, height: int = 40):
        super().__init__(text, parent)
        self.accent = accent
        self.primary = primary
        self.setFixedHeight(height)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(QFont(FONT, 14, QFont.Medium))
        self._apply_style(False)

    def _apply_style(self, pressed: bool):
        if self.primary:
            bg = self.accent if not pressed else self._darken(self.accent)
            style = f"""
                QPushButton {{
                    background: {bg};
                    color: white;
                    border: 1px solid rgba(255,255,255,0.35);
                    border-radius: 13px;
                    padding: 0 18px;
                }}
                QPushButton:hover {{ background: {self._darken(self.accent)}; }}
            """
        else:
            bg = "rgba(255,255,255,0.55)" if not pressed else "rgba(255,255,255,0.85)"
            style = f"""
                QPushButton {{
                    background: {bg};
                    color: {COLORS['ink']};
                    border: 1px solid rgba(255,255,255,0.75);
                    border-radius: 13px;
                    padding: 0 18px;
                }}
                QPushButton:hover {{ background: rgba(255,255,255,0.78); }}
                QPushButton:disabled {{ color: #AEAEB2; background: rgba(255,255,255,0.35); }}
            """
        self.setStyleSheet(style)

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.82) -> str:
        c = QColor(hex_color)
        return f"rgb({int(c.red()*factor)},{int(c.green()*factor)},{int(c.blue()*factor)})"

    def mousePressEvent(self, event):
        self._apply_style(True)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._apply_style(False)
        super().mouseReleaseEvent(event)


class NavButton(QPushButton):
    """侧边栏导航按钮：选中态玻璃高亮 + 左侧色条。"""
    checkedSignal = Signal(str)

    def __init__(self, text: str, key: str, parent=None, accent: str = COLORS["blue"]):
        super().__init__(text, parent)
        self.key = key
        self.accent = accent
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(QFont(FONT, 15, QFont.Medium))
        self.clicked.connect(self._on_clicked)
        self._refresh()

    def _on_clicked(self, _=None):
        self.checkedSignal.emit(self.key)

    def _refresh(self):
        if self.isChecked():
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,0.85);
                    color: {self.accent};
                    border: 1px solid rgba(255,255,255,0.9);
                    border-left: 4px solid {self.accent};
                    border-radius: 12px;
                    text-align: left;
                    padding-left: 16px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {COLORS['secondary']};
                    border: 1px solid transparent;
                    border-radius: 12px;
                    text-align: left;
                    padding-left: 20px;
                }}
                QPushButton:hover {{ background: rgba(255,255,255,0.45); color: {COLORS['ink']}; }}
            """)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._refresh()


# --------------------------------------------------------------------------- #
# 标题与分隔
# --------------------------------------------------------------------------- #
class SectionTitle(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setFont(QFont(FONT, 17, QFont.Bold))
        t.setStyleSheet(f"color:{COLORS['ink']};")
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setFont(QFont(FONT, 12))
            s.setStyleSheet(f"color:{COLORS['secondary']};")
            lay.addWidget(s)


def hline(color: str = "#D6D6DB") -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color:{color}; background:{color};")
    line.setFixedHeight(1)
    return line


# --------------------------------------------------------------------------- #
# 图表（QPainter 自绘，玻璃风格）
# --------------------------------------------------------------------------- #
class DonutChart(QWidget):
    """环形图：segments = [(label, value, color), ...]"""

    def __init__(self, segments: list, center_label: str = "", parent=None):
        super().__init__(parent)
        self.segments = segments
        self.center_label = center_label
        self.setMinimumHeight(190)

    def set_data(self, segments, center_label=""):
        self.segments = segments
        self.center_label = center_label
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # 圆环占左侧，图例占右侧，彻底分离避免重叠
        side = int(min(h - 12, w * 0.44))
        if side <= 20:
            return
        cx, cy = side / 2 + 8, h / 2
        rect = QRectF(cx - side / 2, cy - side / 2, side, side)
        thickness = max(16, int(side * 0.16))

        total = sum(v for _, v, _ in self.segments) or 1
        start = 90  # 12 点方向
        for label, value, color in self.segments:
            if value <= 0:
                continue
            span = 360 * value / total
            pen = QPen(QColor(color), thickness, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(rect, -start * 16, -span * 16)
            start -= span

        # 中心数字（限制在圆环内圈）
        inner = side * 0.62
        painter.setPen(QColor(COLORS["ink"]))
        painter.setFont(QFont(FONT, 24, QFont.Bold))
        painter.drawText(QRectF(cx - inner / 2, cy - 26, inner, 38),
                         Qt.AlignCenter, str(int(total)))
        painter.setPen(QColor(COLORS["secondary"]))
        painter.setFont(QFont(FONT, 11))
        painter.drawText(QRectF(cx - inner / 2, cy + 10, inner, 20),
                         Qt.AlignCenter, self.center_label)

        # 图例（右侧垂直居中）
        legend_x = side + 20
        legend_w = max(90, w - legend_x - 6)
        row_h = 30
        ly = cy - (len(self.segments) * row_h) / 2
        painter.setFont(QFont(FONT, 13))
        for label, value, color in self.segments:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(legend_x, ly + 6, 12, 12), 3, 3)
            painter.setPen(QColor(COLORS["ink"]))
            painter.drawText(QRectF(legend_x + 20, ly, legend_w - 62, 24),
                             Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.setPen(QColor(COLORS["secondary"]))
            painter.drawText(QRectF(legend_x + legend_w - 48, ly, 44, 24),
                             Qt.AlignRight | Qt.AlignVCenter, str(value))
            ly += row_h
        super().paintEvent(event)


class BarChart(QWidget):
    """横向条形图：data = {label: value}"""

    def __init__(self, data: dict, color: str = COLORS["blue"], parent=None):
        super().__init__(parent)
        self.data = data
        self.color = color
        self.setMinimumHeight(max(120, 30 * max(1, len(data)) + 20))

    def set_data(self, data: dict, color: str = None):
        self.data = data
        if color:
            self.color = color
        self.adjustSize()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        if not self.data:
            painter.setPen(QColor(COLORS["secondary"]))
            painter.setFont(QFont(FONT, 13))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            return
        maximum = max(self.data.values()) or 1
        label_w = 88
        value_w = 34
        bar_w = max(20, w - label_w - value_w - 30)
        y = 6
        row_h = 30
        for label, value in self.data.items():
            painter.setPen(QColor(COLORS["secondary"]))
            painter.setFont(QFont(FONT, 12))
            painter.drawText(QRectF(0, y, label_w - 6, 22),
                             Qt.AlignLeft | Qt.AlignVCenter, str(label))
            length = bar_w * value / maximum
            track = QRectF(label_w, y + 5, bar_w, 12)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(120, 120, 128, 28))
            painter.drawRoundedRect(track, 6, 6)
            grad = QLinearGradient(track.topLeft(), track.topRight())
            grad.setColorAt(0, _with_alpha(self.color, 220))
            grad.setColorAt(1, QColor(self.color))
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(label_w, y + 5, max(4, length), 12), 6, 6)
            painter.setPen(QColor(COLORS["ink"]))
            painter.setFont(QFont(FONT, 12, QFont.Medium))
            painter.drawText(QRectF(label_w + bar_w + 8, y, value_w, 22),
                             Qt.AlignLeft | Qt.AlignVCenter, str(value))
            y += row_h
        super().paintEvent(event)


# --------------------------------------------------------------------------- #
# macOS 交通灯窗口控件（关闭 / 最小化 / 全屏）
# --------------------------------------------------------------------------- #
class TrafficLightButton(QPushButton):
    """macOS 风格交通灯圆点。hover 时显示符号，拖动窗口时不误触。"""

    def __init__(self, kind: str, parent=None):
        # kind: close(红) / minimize(黄) / zoom(绿)
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(15, 15)
        self.setCursor(Qt.ArrowCursor)
        self.setFlat(True)
        self._hover = False
        self._palette = {
            "close": ("#FF5F57", "#E0443D"),
            "minimize": ("#FEBC2E", "#E5A028"),
            "zoom": ("#28C840", "#1FA636"),
        }

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        base, dark = self._palette[self.kind]
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = 6.2
        # 外圈细描边，增强立体感
        painter.setPen(QPen(QColor(0, 0, 0, 45), 0.8))
        painter.setBrush(QColor(base))
        painter.drawEllipse(center, radius, radius)
        # 顶部微高光
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawEllipse(QPointF(center.x() - 1.2, center.y() - 1.4), 2.6, 2.2)
        # hover 显示符号
        if self._hover:
            symbol = QColor(0, 0, 0, 190)
            pen = QPen(symbol, 1.5, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            if self.kind == "close":
                painter.drawLine(QLineF(center.x() - 2.6, center.y() - 2.6,
                                        center.x() + 2.6, center.y() + 2.6))
                painter.drawLine(QLineF(center.x() + 2.6, center.y() - 2.6,
                                        center.x() - 2.6, center.y() + 2.6))
            elif self.kind == "minimize":
                painter.drawLine(QLineF(center.x() - 2.8, center.y(),
                                        center.x() + 2.8, center.y()))
            else:  # zoom
                painter.drawLine(QLineF(center.x() - 2.6, center.y() - 2.6,
                                        center.x() + 2.6, center.y() + 2.6))
                painter.drawLine(QLineF(center.x() + 2.6, center.y() - 2.6,
                                        center.x() - 2.6, center.y() + 2.6))
                painter.drawLine(QLineF(center.x() - 2.6, center.y() + 2.6,
                                        center.x() + 2.6, center.y() + 2.6))


class WindowControls(QWidget):
    """交通灯控件容器：红黄绿三圆点，水平排列。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.close_btn = TrafficLightButton("close")
        self.min_btn = TrafficLightButton("minimize")
        self.zoom_btn = TrafficLightButton("zoom")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(9)
        lay.addWidget(self.close_btn)
        lay.addWidget(self.min_btn)
        lay.addWidget(self.zoom_btn)
        lay.addStretch(1)
        self.setFixedWidth(78)
        self.setFixedHeight(18)


# --------------------------------------------------------------------------- #
# 状态胶囊（在职 / 已离职）
# --------------------------------------------------------------------------- #
class StatusPill(QLabel):
    """小型状态标签，如「在职」「已离职」。"""

    def __init__(self, text: str, accent: str, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont(FONT, 12, QFont.Medium))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background:{rgba(accent, 40)}; color:{accent}; "
            f"border-radius:9px; padding:3px 10px;"
        )
