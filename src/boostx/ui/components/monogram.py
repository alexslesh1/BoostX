from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

_ACCENT_COLORS = (
    "#3987E5",
    "#9085E9",
    "#26A69A",
    "#FF8A65",
    "#7CB342",
    "#AB47BC",
    "#5C6BC0",
    "#26C6DA",
)


def _color_for_seed(seed: str) -> QColor:
    index = sum(ord(char) for char in seed) % len(_ACCENT_COLORS)
    return QColor(_ACCENT_COLORS[index])


def _initials(name: str) -> str:
    words = [word for word in name.replace(":", " ").replace("-", " ").split() if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def render_monogram_pixmap(name: str, seed: str, size: QSize) -> QPixmap:
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = _color_for_seed(seed)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    radius = min(size.width(), size.height()) / 4
    painter.drawRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)

    painter.setPen(QColor("#FFFFFF"))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(int(size.height() * 0.42))
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, size.width(), size.height()), Qt.AlignmentFlag.AlignCenter, _initials(name))

    painter.end()
    return pixmap
