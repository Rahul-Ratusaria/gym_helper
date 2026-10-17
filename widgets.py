"""Painted widgets for the Gym Helper desktop interface."""
from collections import deque
from math import pi, sin, cos

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

GREEN = "#b6f36b"
MUTED = "#929b99"
CONNECTIONS = ((11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
               (11, 23), (12, 24), (23, 24), (23, 25), (25, 27),
               (24, 26), (26, 28), (27, 31), (28, 32))


def label(text, role=None):
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    return widget


class Metric(QFrame):
    def __init__(self, title, value="—", subtitle="", accent=False):
        super().__init__()
        self.setObjectName("metric")
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 14, 18, 14)
        box.setSpacing(5)
        box.addWidget(label(title.upper(), "eyebrow"))
        self.value = label(value, "metricAccent" if accent else "metricValue")
        box.addWidget(self.value)
        self.subtitle = label(subtitle, "muted")
        box.addWidget(self.subtitle)


class RepRing(QWidget):
    def __init__(self):
        super().__init__()
        self.reps, self.target = 0, 12
        self.setMinimumHeight(156)

    def set_values(self, reps, target):
        self.reps, self.target = reps, target
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width() - 16, self.height() - 12, 158)
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        p.setPen(QPen(QColor("#303834"), 7))
        p.drawEllipse(rect.adjusted(5, 5, -5, -5))
        p.setPen(QPen(QColor(GREEN), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect.adjusted(5, 5, -5, -5), 90 * 16, -int(360 * 16 * min(1, self.reps / self.target)))
        p.setPen(QColor("#f4f7ef"))
        p.setFont(QFont("Segoe UI", 36, QFont.Weight.DemiBold))
        p.drawText(rect.adjusted(0, -14, 0, 0), Qt.AlignmentFlag.AlignCenter, str(self.reps).zfill(2))
        p.setPen(QColor(MUTED))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(rect.adjusted(0, 58, 0, 0), Qt.AlignmentFlag.AlignCenter, f"of {self.target} reps")


class AngleChart(QWidget):
    def __init__(self):
        super().__init__()
        self.samples = deque(maxlen=700)
        self.low, self.high = 55, 155
        self.setMinimumHeight(125)

    def add(self, timestamp, angle):
        self.samples.append((timestamp, angle))
        while self.samples and timestamp - self.samples[0][0] > 20:
            self.samples.popleft()
        self.update()

    def clear(self):
        self.samples.clear()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(35, 8, max(1, self.width() - 48), max(1, self.height() - 29))
        p.setFont(QFont("Segoe UI", 8))
        for angle in (0, 90, 180):
            y = area.bottom() - angle / 180 * area.height()
            p.setPen(QColor("#303634"))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, y - 9, 28, 18), Qt.AlignmentFlag.AlignRight, f"{angle}°")
        p.setPen(QPen(QColor("#576b43"), 1, Qt.PenStyle.DashLine))
        for endpoint in (self.low, self.high):
            y = area.bottom() - endpoint / 180 * area.height()
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        if not self.samples:
            p.setPen(QColor(MUTED))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "Your movement trace will appear here")
        else:
            end = self.samples[-1][0]
            path = QPainterPath()
            connected = False
            for stamp, angle in self.samples:
                if angle is None:
                    connected = False
                    continue
                point = QPointF(area.right() - (end - stamp) / 20 * area.width(), area.bottom() - angle / 180 * area.height())
                if connected:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    connected = True
            p.setPen(QPen(QColor(GREEN), 2))
            p.drawPath(path)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(area.left(), area.bottom() + 6, area.width(), 15), Qt.AlignmentFlag.AlignRight, "last 20 seconds")


class VideoCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(380, 255)
        self.image = None
        self.points = []
        self.highlight = (11, 13, 15)
        self.mirror = True
        self.skeleton = True
        self.banner = "CAMERA STANDBY"
        self.center_title = "Your space. Your pace."
        self.center_detail = "Choose an exercise and start your session."
        self.overlay = ""
        self.is_demo = False

    def set_frame(self, rgb, landmarks):
        if rgb is not None:
            h, w, _ = rgb.shape
            self.image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        else:
            self.image = None
        self.points = landmarks
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(outer, 16, 16)
        p.setClipPath(clip)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#232e27"))
        gradient.setColorAt(1, QColor("#101714"))
        p.fillRect(outer, gradient)
        aspect = self.image.width() / self.image.height() if self.image else 16 / 9
        w, h = self.width(), self.width() / aspect
        if h > self.height():
            h, w = self.height(), self.height() * aspect
        target = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        if self.image:
            p.save()
            if self.mirror:
                p.translate(self.width(), 0)
                p.scale(-1, 1)
            p.drawImage(target, self.image)
            p.restore()
        else:
            p.setPen(QPen(QColor("#29372e"), 1))
            for x in range(0, self.width(), 36):
                p.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), 36):
                p.drawLine(0, y, self.width(), y)
            if not self.points:
                cx, cy = self.width() / 2, self.height() / 2 - 42
                p.setPen(QPen(QColor("#435d46"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawEllipse(QPointF(cx, cy - 38), 16, 16)
                for a, b in (((cx, cy - 17), (cx, cy + 48)), ((cx - 38, cy + 10), (cx + 38, cy + 10)),
                             ((cx, cy + 48), (cx - 29, cy + 91)), ((cx, cy + 48), (cx + 29, cy + 91))):
                    p.drawLine(QPointF(*a), QPointF(*b))
                p.setPen(QColor("#f1f6ee"))
                p.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
                p.drawText(QRectF(15, cy + 108, self.width() - 30, 34), Qt.AlignmentFlag.AlignCenter, self.center_title)
                p.setPen(QColor("#a6b3a8"))
                p.setFont(QFont("Segoe UI", 10))
                p.drawText(QRectF(15, cy + 145, self.width() - 30, 24), Qt.AlignmentFlag.AlignCenter, self.center_detail)
        if self.skeleton and self.points:
            def pos(index):
                point = self.points[index]
                x = 1 - point[0] if self.mirror else point[0]
                return QPointF(target.x() + x * target.width(), target.y() + point[1] * target.height())
            for a, b in CONNECTIONS:
                if min(self.points[a][3], self.points[b][3]) < .65:
                    continue
                selected = a in self.highlight and b in self.highlight
                p.setPen(QPen(QColor(GREEN if selected else "#d6e7df"), 5 if selected else 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(pos(a), pos(b))
            for index in (0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28):
                if self.points[index][3] >= .65:
                    p.setPen(QPen(QColor("#17241b"), 2))
                    p.setBrush(QColor(GREEN if index in self.highlight else "#d6e7df"))
                    p.drawEllipse(pos(index), 5, 5)
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(14, 22, 17, 220))
        p.drawRoundedRect(QRectF(18, 18, min(self.width() - 36, 245), 30), 8, 8)
        p.setPen(QColor(GREEN))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        p.drawText(QRectF(29, 18, self.width() - 50, 30), Qt.AlignmentFlag.AlignVCenter, self.banner)
        if self.overlay:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(10, 17, 12, 225))
            p.drawRoundedRect(QRectF(20, self.height() - 67, self.width() - 40, 47), 10, 10)
            p.setPen(QColor("#eff5e9"))
            p.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
            p.drawText(QRectF(30, self.height() - 67, self.width() - 60, 47), Qt.AlignmentFlag.AlignCenter, self.overlay)


STYLE = """
* { font-family: 'Segoe UI'; font-size: 13px; color: #edf2e9; }
QMainWindow, QWidget#root { background: #111512; }
QFrame#sidebar { background: #191e1a; border-right: 1px solid #2b332c; }
QLabel#brand { font-size: 24px; font-weight: 750; letter-spacing: -1px; }
QLabel#logo { background: #b6f36b; color: #14200d; border-radius: 10px; font-size: 25px; font-weight: 800; }
QLabel#pageTitle { font-size: 27px; font-weight: 650; letter-spacing: -1px; }
QLabel#sectionTitle { font-size: 16px; font-weight: 600; }
QLabel#eyebrow { color: #95a18f; font-size: 10px; font-weight: 600; letter-spacing: 1.4px; }
QLabel#muted { color: #929b99; font-size: 12px; }
QLabel#small { color: #929b99; font-size: 11px; }
QLabel#metricValue, QLabel#metricAccent { font-size: 29px; font-weight: 650; }
QLabel#metricAccent { color: #b6f36b; }
QLabel#badge { color: #b6f36b; background: #23301e; border: 1px solid #3b4d2d; border-radius: 13px; padding: 7px 12px; font-size: 10px; font-weight: 600; }
QLabel#coachTitle { font-size: 18px; font-weight: 600; }
QLabel#summary { font-size: 15px; color: #b6f36b; }
QFrame#card, QFrame#metric { background: #1c221e; border: 1px solid #303830; border-radius: 13px; }
QFrame#coach { background: #22301e; border: 1px solid #3d5330; border-radius: 13px; }
QFrame#coach[warning="true"] { background: #342c1d; border-color: #75603b; }
QPushButton { background: #2a322b; border: 1px solid #3b463c; border-radius: 8px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #364337; border-color: #627859; }
QPushButton:pressed { background: #42553c; }
QPushButton:disabled { color: #647063; background: #222823; border-color: #303830; }
QPushButton#primary { background: #b6f36b; color: #16220e; border-color: #b6f36b; }
QPushButton#primary:hover { background: #c8ff87; }
QPushButton#primary:disabled { background: #4b6137; color: #9ba98d; border-color: #4b6137; }
QPushButton#quiet { background: transparent; color: #aebba8; border: 1px solid #3b463c; }
QPushButton#nav { background: transparent; border: none; color: #9ca898; text-align: left; padding: 13px 16px; }
QPushButton#nav:checked { color: #c7f79e; background: #2a3823; }
QPushButton#nav:hover { background: #263025; }
QComboBox, QSpinBox { background: #121813; border: 1px solid #3c473b; border-radius: 7px; min-height: 20px; padding: 8px; selection-background-color: #3b5630; }
QComboBox:focus, QSpinBox:focus { border-color: #b6f36b; }
QComboBox:disabled, QSpinBox:disabled { color: #6e7c69; }
QComboBox QAbstractItemView { background: #232d23; border: 1px solid #50634a; selection-background-color: #3b5630; }
QCheckBox { spacing: 8px; padding: 3px 0; color: #bdc7b9; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #62745b; border-radius: 4px; background: #151c15; }
QCheckBox::indicator:checked { background: #b6f36b; border-color: #b6f36b; }
QProgressBar { border: none; border-radius: 3px; background: #303a2c; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: #b6f36b; border-radius: 3px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #4b5d44; border-radius: 3px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTableWidget { background: #1c221e; alternate-background-color: #202821; border: 1px solid #303830; border-radius: 10px; gridline-color: #303830; selection-background-color: #344c29; }
QTableWidget::item { padding: 12px; border-bottom: 1px solid #303830; }
QHeaderView::section { background: #252f24; color: #b9c8b1; padding: 12px; border: none; font-weight: 600; }
QTextBrowser { background: #1c221e; border: 1px solid #303830; border-radius: 10px; padding: 18px; selection-background-color: #3b5630; }
QToolTip { background: #33442b; color: #eff9e8; border: 1px solid #5e784e; padding: 8px; }
QStatusBar { background: #151c16; color: #a6b3a0; }
QMessageBox { background: #1c221e; }
"""
