from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def render_tinted_pixmap(svg_path: Path, color: str, size: QSize) -> QPixmap:
    renderer = QSvgRenderer(str(svg_path))
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap
