"""Small symbolic icons used by the Track Editor tool palette.

The icons are drawn at runtime with Qt so the project does not depend on
external image files.  They intentionally communicate shape/function rather
than displaying long button labels.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)


FG = QColor(225, 230, 235)
ROAD = QColor(92, 96, 102)
ROAD_EDGE = QColor(230, 232, 235)
ROAD_CENTER = QColor(245, 205, 55)
ACCENT = QColor(75, 170, 235)
DANGER = QColor(220, 75, 75)
GREEN = QColor(75, 200, 120)
AMBER = QColor(235, 165, 60)
PURPLE = QColor(190, 105, 235)


def _road_pen(width: float = 8.0) -> QPen:
    pen = QPen(ROAD, width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def make_tool_icon(kind: str, size: int = 30) -> QIcon:
    """Return a compact, dark-theme-friendly icon for *kind*."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    s = float(size)
    cx = s / 2.0
    cy = s / 2.0

    # ------------------------------------------------------------
    # Roads
    # ------------------------------------------------------------
    if kind == "straight":
        p.setPen(_road_pen(9))
        p.drawLine(QPointF(4, cy), QPointF(s - 4, cy))
        pen = QPen(ROAD_CENTER, 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(QPointF(4, cy), QPointF(s - 4, cy))

    elif kind in {"curve45", "curve90"}:
        p.setPen(_road_pen(8))
        rect = QRectF(3, 3, s - 7, s - 7)
        span = -45 * 16 if kind == "curve45" else -90 * 16
        p.drawArc(rect, 90 * 16, span)
        pen = QPen(ROAD_CENTER, 1.3, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, span)

    elif kind == "tjunction":
        p.setPen(_road_pen(8))
        p.drawLine(QPointF(4, 8), QPointF(s - 4, 8))
        p.drawLine(QPointF(cx, 8), QPointF(cx, s - 4))

    elif kind == "intersection":
        p.setPen(_road_pen(8))
        p.drawLine(QPointF(4, cy), QPointF(s - 4, cy))
        p.drawLine(QPointF(cx, 4), QPointF(cx, s - 4))

    elif kind == "road_end":
        p.setPen(_road_pen(8))
        p.drawLine(QPointF(4, cy), QPointF(s - 8, cy))
        p.setPen(QPen(ROAD_EDGE, 2.5))
        p.drawLine(QPointF(s - 8, 6), QPointF(s - 8, s - 6))

    # ------------------------------------------------------------
    # Traffic / environment
    # ------------------------------------------------------------
    elif kind == "traffic_light":
        body = QRectF(cx - 6, 3, 12, s - 6)
        p.setPen(QPen(FG, 1.2))
        p.setBrush(QColor(45, 48, 52))
        p.drawRoundedRect(body, 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        for y, color in ((9, DANGER), (15, ROAD_CENTER), (21, GREEN)):
            p.setBrush(color)
            p.drawEllipse(QPointF(cx, y), 2.7, 2.7)

    elif kind == "stop":
        r = 10.5
        pts = []
        for i in range(8):
            import math
            a = math.radians(22.5 + i * 45)
            pts.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
        p.setPen(QPen(FG, 1.2))
        p.setBrush(DANGER)
        p.drawPolygon(QPolygonF(pts))
        p.setPen(QPen(Qt.GlobalColor.white, 1))
        p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))

    elif kind == "yield":
        pts = QPolygonF([
            QPointF(cx, 4),
            QPointF(s - 5, s - 5),
            QPointF(5, s - 5),
        ])
        p.setPen(QPen(DANGER, 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(pts)

    elif kind == "roundabout":
        p.setPen(QPen(ACCENT, 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(6, 6, s - 12, s - 12), 25 * 16, 290 * 16)
        p.setBrush(ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(s - 5, 11),
            QPointF(s - 11, 9),
            QPointF(s - 8, 15),
        ]))

    elif kind == "traffic_sign_catalog":
        p.setPen(QPen(DANGER, 2.2))
        p.setBrush(QColor(245, 245, 238))
        p.drawEllipse(QRectF(5, 5, s - 10, s - 10))
        p.setPen(QPen(QColor(35, 35, 35), 1.4))
        font = p.font()
        font.setBold(True)
        font.setPointSize(7)
        p.setFont(font)
        p.drawText(QRectF(5, 5, s - 10, s - 10), Qt.AlignmentFlag.AlignCenter, "24")

    elif kind == "crosswalk":
        p.setPen(QPen(FG, 1))
        p.setBrush(QColor(70, 73, 78))
        p.drawRect(QRectF(4, 7, s - 8, s - 14))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(FG)
        for x in (7, 12, 17, 22):
            p.drawRect(QRectF(x, 8, 2.5, s - 16))

    elif kind == "building":
        p.setPen(QPen(FG, 1.5))
        p.setBrush(QColor(95, 115, 135))
        p.drawRect(QRectF(6, 5, s - 12, s - 9))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(180, 215, 235))
        for yy in (9, 15):
            for xx in (10, 16, 22):
                p.drawRect(QRectF(xx, yy, 3, 3))

    elif kind == "office":
        p.setPen(QPen(FG, 1.3))
        p.setBrush(QColor(65, 90, 125))
        p.drawRect(QRectF(7, 4, s - 14, s - 8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(150, 205, 235))
        for yy in (8, 14, 20):
            for xx in (11, 18):
                p.drawRect(QRectF(xx, yy, 4, 3))

    elif kind == "apartment":
        p.setPen(QPen(FG, 1.3))
        p.setBrush(QColor(168, 145, 110))
        p.drawRect(QRectF(5, 6, s - 10, s - 10))
        p.setPen(QPen(QColor(80, 82, 85), 1.4))
        for yy in (11, 17, 23):
            p.drawLine(QPointF(6, yy), QPointF(s - 6, yy))

    elif kind == "shop":
        p.setPen(QPen(FG, 1.3))
        p.setBrush(QColor(150, 60, 55))
        p.drawRect(QRectF(4, 9, s - 8, s - 13))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(145, 205, 230))
        p.drawRect(QRectF(7, 14, 8, 8))
        p.drawRect(QRectF(17, 14, 8, 8))
        p.setBrush(AMBER)
        p.drawRect(QRectF(7, 6, s - 14, 4))

    elif kind == "tower":
        p.setPen(QPen(FG, 1.2))
        p.setBrush(QColor(95, 105, 125))
        p.drawRect(QRectF(5, 18, s - 10, 8))
        p.drawRect(QRectF(8, 11, s - 16, 8))
        p.drawRect(QRectF(11, 5, s - 22, 7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(165, 210, 235))
        for xx in (8, 15, 22):
            p.drawRect(QRectF(xx, 20, 3, 3))
        p.setBrush(QColor(45, 38, 32))
        p.drawRect(QRectF(cx - 2, 21, 4, 5))

    elif kind == "tree":
        p.setPen(QPen(QColor(55, 85, 55), 1.2))
        p.setBrush(QColor(65, 155, 80))
        p.drawEllipse(QPointF(cx - 4, cy), 7, 7)
        p.drawEllipse(QPointF(cx + 4, cy), 7, 7)
        p.drawEllipse(QPointF(cx, cy - 5), 7, 7)
        p.setBrush(QColor(105, 70, 40))
        p.drawEllipse(QPointF(cx, cy + 2), 2.5, 2.5)

    elif kind == "pine":
        p.setPen(QPen(QColor(45, 95, 55), 1.2))
        p.setBrush(QColor(45, 125, 65))
        p.drawPolygon(QPolygonF([QPointF(cx, 3), QPointF(s - 4, 25), QPointF(4, 25)]))
        p.setBrush(QColor(105, 70, 40))
        p.drawRect(QRectF(cx - 2, 22, 4, 5))

    elif kind == "bench":
        p.setPen(QPen(QColor(75, 55, 40), 1.5))
        p.setBrush(QColor(155, 95, 45))
        p.drawRoundedRect(QRectF(4, 10, s - 8, 8), 2, 2)
        p.setPen(QPen(FG, 1.5))
        p.drawLine(QPointF(8, 18), QPointF(8, 25))
        p.drawLine(QPointF(s - 8, 18), QPointF(s - 8, 25))

    elif kind == "lamp":
        p.setPen(QPen(FG, 2.2))
        p.drawLine(QPointF(cx, 25), QPointF(cx, 9))
        p.setBrush(QColor(245, 225, 145))
        p.drawEllipse(QPointF(cx, 7), 5, 5)
        p.drawLine(QPointF(cx - 5, 26), QPointF(cx + 5, 26))

    elif kind == "bin":
        p.setPen(QPen(FG, 1.4))
        p.setBrush(QColor(45, 120, 75))
        p.drawRoundedRect(QRectF(8, 8, s - 16, s - 12), 2, 2)
        p.drawLine(QPointF(7, 8), QPointF(s - 7, 8))

    elif kind == "planter":
        p.setPen(QPen(FG, 1.2))
        p.setBrush(QColor(145, 85, 45))
        p.drawRect(QRectF(4, 15, s - 8, 10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(GREEN)
        p.drawEllipse(QPointF(11, 13), 5, 5)
        p.drawEllipse(QPointF(20, 12), 6, 6)

    elif kind == "fountain":
        p.setPen(QPen(FG, 1.3))
        p.setBrush(QColor(100, 110, 120))
        p.drawEllipse(QPointF(cx, cy), 12, 12)
        p.setPen(QPen(QColor(90, 180, 235), 2))
        p.setBrush(QColor(65, 135, 205))
        p.drawEllipse(QPointF(cx, cy), 8, 8)
        p.setBrush(FG)
        p.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

    # ------------------------------------------------------------
    # Experiment / vehicles
    # ------------------------------------------------------------
    elif kind == "person":
        p.setPen(QPen(ACCENT, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, 7), 3.2, 3.2)
        p.drawLine(QPointF(cx, 11), QPointF(cx, 20))
        p.drawLine(QPointF(cx, 14), QPointF(cx - 6, 17))
        p.drawLine(QPointF(cx, 14), QPointF(cx + 6, 17))
        p.drawLine(QPointF(cx, 20), QPointF(cx - 5, 26))
        p.drawLine(QPointF(cx, 20), QPointF(cx + 5, 26))

    elif kind == "animal":
        p.setPen(QPen(FG, 1.6))
        p.setBrush(AMBER)
        p.drawEllipse(QRectF(6, 10, 15, 9))
        p.drawEllipse(QRectF(19, 8, 7, 7))
        p.drawLine(QPointF(9, 18), QPointF(8, 25))
        p.drawLine(QPointF(18, 18), QPointF(19, 25))

    elif kind == "trigger":
        pen = QPen(PURPLE, 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 10, 10)
        p.setPen(QPen(PURPLE, 1.7))
        p.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
        p.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))

    elif kind in {"qcar_start", "qcar_env"}:
        body = QRectF(5, 9, s - 12, 12)
        p.setPen(QPen(FG, 1.3))
        p.setBrush(ACCENT if kind == "qcar_start" else AMBER)
        p.drawRoundedRect(body, 3, 3)
        p.setPen(QPen(ROAD_CENTER, 2))
        p.drawLine(QPointF(s - 7, cy), QPointF(s - 2, cy))
        p.drawLine(QPointF(s - 5, cy - 3), QPointF(s - 2, cy))
        p.drawLine(QPointF(s - 5, cy + 3), QPointF(s - 2, cy))
        if kind == "qcar_env":
            p.setPen(QPen(AMBER, 1.2, Qt.PenStyle.DashLine))
            p.drawArc(QRectF(3, 3, s - 6, s - 6), 190 * 16, 80 * 16)

    # ------------------------------------------------------------
    # Editing / utility
    # ------------------------------------------------------------
    elif kind == "undo":
        p.setPen(QPen(ACCENT, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(7, 7, s - 12, s - 12), 35 * 16, 250 * 16)
        p.setBrush(ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(6, 9), QPointF(12, 5), QPointF(12, 13)
        ]))

    elif kind == "duplicate":
        p.setPen(QPen(FG, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(6, 8, 13, 13))
        p.drawRect(QRectF(11, 4, 13, 13))

    elif kind == "rotate":
        p.setPen(QPen(ACCENT, 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(6, 6, s - 12, s - 12), 20 * 16, 285 * 16)
        p.setBrush(ACCENT)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(24, 6), QPointF(18, 5), QPointF(22, 11)
        ]))

    elif kind == "delete":
        p.setPen(QPen(DANGER, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(9, 10, 12, 14))
        p.drawLine(QPointF(7, 8), QPointF(23, 8))
        p.drawLine(QPointF(12, 5), QPointF(18, 5))

    elif kind == "autofill":
        # Scatter a small building/tree group around an open-space sparkle.
        p.setPen(QPen(FG, 1.2))
        p.setBrush(QColor(95, 115, 135))
        p.drawRect(QRectF(4, 15, 8, 10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(GREEN)
        p.drawEllipse(QPointF(21, 20), 5, 5)
        p.setBrush(QColor(105, 70, 40))
        p.drawRect(QRectF(20, 22, 2, 4))
        p.setPen(QPen(ROAD_CENTER, 1.7))
        p.drawLine(QPointF(18, 5), QPointF(18, 11))
        p.drawLine(QPointF(15, 8), QPointF(21, 8))
        p.drawLine(QPointF(24, 7), QPointF(27, 4))
        p.drawLine(QPointF(24, 7), QPointF(27, 10))

    elif kind == "export":
        p.setPen(QPen(GREEN, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, 5), QPointF(cx, 19))
        p.drawLine(QPointF(cx, 5), QPointF(cx - 5, 10))
        p.drawLine(QPointF(cx, 5), QPointF(cx + 5, 10))
        p.drawLine(QPointF(6, 20), QPointF(6, 25))
        p.drawLine(QPointF(6, 25), QPointF(s - 6, 25))
        p.drawLine(QPointF(s - 6, 25), QPointF(s - 6, 20))

    elif kind == "fit":
        p.setPen(QPen(FG, 1.8))
        p.drawLine(QPointF(5, 11), QPointF(5, 5)); p.drawLine(QPointF(5, 5), QPointF(11, 5))
        p.drawLine(QPointF(s-5, 11), QPointF(s-5, 5)); p.drawLine(QPointF(s-5, 5), QPointF(s-11, 5))
        p.drawLine(QPointF(5, s-11), QPointF(5, s-5)); p.drawLine(QPointF(5, s-5), QPointF(11, s-5))
        p.drawLine(QPointF(s-5, s-11), QPointF(s-5, s-5)); p.drawLine(QPointF(s-5, s-5), QPointF(s-11, s-5))

    elif kind == "snap":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(GREEN)
        p.drawEllipse(QPointF(8, cy), 4, 4)
        p.drawEllipse(QPointF(s - 8, cy), 4, 4)
        p.setPen(QPen(GREEN, 2, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(12, cy), QPointF(s - 12, cy))

    else:
        p.setPen(QPen(FG, 2))
        p.drawEllipse(QPointF(cx, cy), 8, 8)

    p.end()
    return QIcon(pixmap)
