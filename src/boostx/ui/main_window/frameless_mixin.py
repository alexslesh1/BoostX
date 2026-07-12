from enum import IntFlag, auto

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent

from boostx.config.layout import LayoutConstants


class ResizeEdge(IntFlag):
    NONE = 0
    LEFT = auto()
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()


_CURSOR_BY_EDGE = {
    ResizeEdge.LEFT: Qt.CursorShape.SizeHorCursor,
    ResizeEdge.RIGHT: Qt.CursorShape.SizeHorCursor,
    ResizeEdge.TOP: Qt.CursorShape.SizeVerCursor,
    ResizeEdge.BOTTOM: Qt.CursorShape.SizeVerCursor,
    ResizeEdge.LEFT | ResizeEdge.TOP: Qt.CursorShape.SizeFDiagCursor,
    ResizeEdge.RIGHT | ResizeEdge.BOTTOM: Qt.CursorShape.SizeFDiagCursor,
    ResizeEdge.RIGHT | ResizeEdge.TOP: Qt.CursorShape.SizeBDiagCursor,
    ResizeEdge.LEFT | ResizeEdge.BOTTOM: Qt.CursorShape.SizeBDiagCursor,
}


class FramelessWindowMixin:
    def init_frameless(self) -> None:
        self.setMouseTracking(True)
        self._resize_margin = LayoutConstants().RESIZE_MARGIN
        self._resize_edge = ResizeEdge.NONE
        self._is_resizing = False
        self._resize_start_geometry = QRect()
        self._resize_start_mouse = QPoint()

    def _edge_at(self, pos: QPoint) -> ResizeEdge:
        edge = ResizeEdge.NONE
        rect = self.rect()
        margin = self._resize_margin
        if pos.x() <= margin:
            edge |= ResizeEdge.LEFT
        elif pos.x() >= rect.width() - margin:
            edge |= ResizeEdge.RIGHT
        if pos.y() <= margin:
            edge |= ResizeEdge.TOP
        elif pos.y() >= rect.height() - margin:
            edge |= ResizeEdge.BOTTOM
        return edge

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.isMaximized() and event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge != ResizeEdge.NONE:
                self._is_resizing = True
                self._resize_edge = edge
                self._resize_start_geometry = self.geometry()
                self._resize_start_mouse = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_resizing:
            self._perform_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if not self.isMaximized():
            edge = self._edge_at(event.position().toPoint())
            self.setCursor(_CURSOR_BY_EDGE.get(edge, Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_resizing:
            self._is_resizing = False
            self._resize_edge = ResizeEdge.NONE
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _perform_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._resize_start_mouse
        rect = QRect(self._resize_start_geometry)
        if self._resize_edge & ResizeEdge.LEFT:
            rect.setLeft(rect.left() + delta.x())
        if self._resize_edge & ResizeEdge.RIGHT:
            rect.setRight(rect.right() + delta.x())
        if self._resize_edge & ResizeEdge.TOP:
            rect.setTop(rect.top() + delta.y())
        if self._resize_edge & ResizeEdge.BOTTOM:
            rect.setBottom(rect.bottom() + delta.y())

        min_size = self.minimumSize()
        if rect.width() < min_size.width():
            if self._resize_edge & ResizeEdge.LEFT:
                rect.setLeft(rect.right() - min_size.width())
            else:
                rect.setRight(rect.left() + min_size.width())
        if rect.height() < min_size.height():
            if self._resize_edge & ResizeEdge.TOP:
                rect.setTop(rect.bottom() - min_size.height())
            else:
                rect.setBottom(rect.top() + min_size.height())

        self.setGeometry(rect)
