"""Graphics view: adaptive grid, workspace overlay, waypoint paths, zoom and pan."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsView

from config import (
    PIXELS_PER_METER,
    WORKSPACE_OPEN_ROAD,
    WORKSPACE_CITYSCAPE,
    WORKSPACE_CITYSCAPE_LITE,
    WORKSPACE_TOWNSCAPE,
    WORKSPACE_TOWNSCAPE_LITE,
)
from core.geometry import scene_to_world, world_to_scene
from items.experiment import ExperimentActorItem, SecondaryQCarItem
from ui.scene import TrackScene

class TrackView(QGraphicsView):
    def __init__(self, scene: TrackScene):
        super().__init__(scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._dark_theme = True
        self._theme_colors = {}
        self.set_dark_theme(True)

        self.editor_window = scene.window
        self._middle_panning = False
        self._last_pan_pos = None

    def set_dark_theme(self, dark: bool):
        """Keep the drawing surface in sync with the application theme."""
        self._dark_theme = bool(dark)
        if self._dark_theme:
            self._theme_colors = {
                "outside": QColor(15, 17, 21),
                "inside": QColor(27, 31, 38, 220),
                "minor": QColor(43, 49, 59),
                "major": QColor(61, 70, 83),
                "border": QColor(73, 162, 220),
                "x_axis": QColor(210, 80, 92),
                "y_axis": QColor(67, 154, 222),
            }
        else:
            self._theme_colors = {
                "outside": QColor(205, 212, 218),
                "inside": QColor(239, 242, 244, 225),
                "minor": QColor(213, 219, 224),
                "major": QColor(183, 193, 201),
                "border": QColor(31, 126, 174),
                "x_axis": QColor(190, 64, 72),
                "y_axis": QColor(31, 120, 184),
            }
        self.setBackgroundBrush(self._theme_colors["outside"])
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF):
        # Everything outside the user-defined editable canvas is deliberately
        # darker. The grid, workspace overlay, and axes are clipped to the
        # editable rectangle so the design boundary is always obvious.
        colors = self._theme_colors
        painter.fillRect(rect, colors["outside"])

        # Workspace references are context rather than editable objects, so let
        # them remain visible outside the editable rectangle. This preserves the
        # Open Road inspection workflow while still making the actual design
        # boundary explicit.
        self.editor_window.draw_workspace_reference(painter, rect)
        self.editor_window.draw_workspace_platform_reference(painter, rect)

        editable_rect = self.scene().editable_area_rect()
        draw_rect = rect.intersected(editable_rect)
        if draw_rect.isEmpty():
            border_pen = QPen(colors["border"], 2, Qt.PenStyle.DashLine)
            border_pen.setCosmetic(True)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(editable_rect)
            return

        painter.save()
        painter.setClipRect(editable_rect)
        # Mapped workspaces already contain a placement reference. Keep the
        # canvas tint light enough that the map remains usable; custom/native
        # modes retain the stronger theme-aware editor fill.
        mapped_mode = self.editor_window.workspace_mode in (
            WORKSPACE_OPEN_ROAD,
            WORKSPACE_CITYSCAPE,
            WORKSPACE_CITYSCAPE_LITE,
            WORKSPACE_TOWNSCAPE,
            WORKSPACE_TOWNSCAPE_LITE,
        )
        canvas_color = QColor(colors["inside"])
        if mapped_mode:
            canvas_color.setAlpha(38)
        painter.fillRect(draw_rect, canvas_color)

        # Adaptive grid: large canvases/Open Road automatically use coarser
        # spacing so the scene remains responsive while zoomed out.
        view_scale = max(abs(self.transform().m11()), 1e-9)
        grid_candidates_m = (
            1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0,
            500.0, 1000.0, 2500.0,
        )

        grid_m = grid_candidates_m[-1]
        for candidate_m in grid_candidates_m:
            if candidate_m * PIXELS_PER_METER * view_scale >= 16.0:
                grid_m = candidate_m
                break

        grid_px = grid_m * PIXELS_PER_METER
        left = math.floor(draw_rect.left() / grid_px) * grid_px
        top = math.floor(draw_rect.top() / grid_px) * grid_px

        minor_lines = []
        major_lines = []

        x = left
        line_index = int(round(left / grid_px))
        while x <= draw_rect.right():
            target = major_lines if line_index % 5 == 0 else minor_lines
            target.append((QPointF(x, draw_rect.top()), QPointF(x, draw_rect.bottom())))
            x += grid_px
            line_index += 1

        y = top
        line_index = int(round(top / grid_px))
        while y <= draw_rect.bottom():
            target = major_lines if line_index % 5 == 0 else minor_lines
            target.append((QPointF(draw_rect.left(), y), QPointF(draw_rect.right(), y)))
            y += grid_px
            line_index += 1

        minor_color = QColor(colors["minor"])
        if mapped_mode:
            minor_color.setAlpha(105)
        minor_pen = QPen(minor_color, 1)
        minor_pen.setCosmetic(True)
        painter.setPen(minor_pen)
        for p1, p2 in minor_lines:
            painter.drawLine(p1, p2)

        major_color = QColor(colors["major"])
        if mapped_mode:
            major_color.setAlpha(135)
        major_pen = QPen(major_color, 1)
        major_pen.setCosmetic(True)
        painter.setPen(major_pen)
        for p1, p2 in major_lines:
            painter.drawLine(p1, p2)

        # World axes stay visible above the grid/reference.
        x_axis_pen = QPen(colors["x_axis"], 2)
        x_axis_pen.setCosmetic(True)
        painter.setPen(x_axis_pen)
        painter.drawLine(
            QPointF(draw_rect.left(), 0),
            QPointF(draw_rect.right(), 0),
        )

        y_axis_pen = QPen(colors["y_axis"], 2)
        y_axis_pen.setCosmetic(True)
        painter.setPen(y_axis_pen)
        painter.drawLine(
            QPointF(0, draw_rect.top()),
            QPointF(0, draw_rect.bottom()),
        )
        painter.restore()

        # Dashed cyan frame = editable design boundary.
        border_pen = QPen(colors["border"], 2, Qt.PenStyle.DashLine)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(editable_rect)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)

        if getattr(self.editor_window, "continuous_road_drawing", False):
            points = list(
                getattr(self.editor_window, "continuous_road_points", [])
            )
            preview = getattr(self.editor_window, "continuous_road_preview", None)
            preview_points = points + ([preview] if preview is not None else [])
            preview_pen = QPen(QColor(45, 205, 235, 235), 3.0)
            preview_pen.setCosmetic(True)
            preview_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(preview_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for start, end in zip(preview_points, preview_points[1:]):
                painter.drawLine(start, end)

            node_radius = 6.0 / max(0.15, self.transform().m11())
            painter.setPen(QPen(QColor(235, 250, 255), 1.5))
            painter.setBrush(QColor(40, 185, 225))
            for point in points:
                painter.drawEllipse(point, node_radius, node_radius)

        editing_id = getattr(self.editor_window, "path_edit_actor_id", None)
        for item in self.scene().track_items():
            if not isinstance(item, ExperimentActorItem):
                continue
            if not item.path_points_m:
                continue

            selected = item.isSelected() or str(item.object_id) == str(editing_id)
            color = QColor(255, 185, 65, 235) if isinstance(item, SecondaryQCarItem) else QColor(190, 110, 255, 220)
            if not selected:
                color.setAlpha(120)

            path_pen = QPen(color, 2.5 if selected else 1.5)
            path_pen.setCosmetic(True)
            painter.setPen(path_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            points = [item.scenePos()] + [world_to_scene(p[0], p[1]) for p in item.path_points_m]
            for i in range(len(points)-1):
                painter.drawLine(points[i], points[i+1])

            pin_radius = 6.0 / max(0.15, self.transform().m11())
            painter.setBrush(color)
            for idx, point in enumerate(points[1:], start=1):
                painter.drawEllipse(point, pin_radius, pin_radius)

    def wheelEvent(self, event):
        zoom_in = 1.15
        zoom_out = 1.0 / zoom_in
        factor = zoom_in if event.angleDelta().y() > 0 else zoom_out

        current_scale = self.transform().m11()
        next_scale = current_scale * factor

        if 0.001 <= next_scale <= 8.0:
            self.scale(factor, factor)
            self.editor_window.update_zoom_label()

        event.accept()

    def mousePressEvent(self, event):
        if getattr(self.editor_window, "continuous_road_drawing", False):
            if event.button() == Qt.MouseButton.LeftButton:
                self.editor_window.add_continuous_road_node(
                    self.mapToScene(event.position().toPoint())
                )
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.editor_window.finish_continuous_road_drawing()
                event.accept()
                return

        if getattr(self.editor_window, "path_edit_actor_id", None):
            if event.button() == Qt.MouseButton.LeftButton:
                self.editor_window.add_movement_waypoint(
                    self.mapToScene(event.position().toPoint())
                )
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.editor_window.finish_path_editing()
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # Snapshot before Qt starts a possible drag. A selection-only click
            # produces identical before/after project data and is discarded.
            self.editor_window.begin_canvas_undo("Move item")

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._middle_panning and self._last_pan_pos is not None:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()

            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        x_m, y_m = scene_to_world(scene_pos)
        self.editor_window.update_cursor_label(x_m, y_m)
        if getattr(self.editor_window, "continuous_road_drawing", False):
            self.editor_window.update_continuous_road_preview(scene_pos)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_panning = False
            self._last_pan_pos = None
            self.unsetCursor()
            event.accept()
            return

        super().mouseReleaseEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            self.editor_window.end_canvas_undo()

    def keyPressEvent(self, event):
        if getattr(self.editor_window, "continuous_road_drawing", False):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.editor_window.finish_continuous_road_drawing()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.editor_window.cancel_continuous_road_drawing()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Backspace:
                self.editor_window.remove_last_continuous_road_node()
                event.accept()
                return
        super().keyPressEvent(event)
