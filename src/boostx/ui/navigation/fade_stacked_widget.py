from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget

_FADE_DURATION_MS = 180


class FadeStackedWidget(QStackedWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageStack")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._animation: QPropertyAnimation | None = None

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex():
            return
        super().setCurrentIndex(index)
        self._fade_in_current_widget()

    def _fade_in_current_widget(self) -> None:
        widget = self.currentWidget()
        if widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(_FADE_DURATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        # Clear the effect once fully opaque — leaving it attached would permanently route this
        # widget's painting through an (idle) QGraphicsEffect, which conflicts with any nested
        # QGraphicsEffect animation deeper in its own child tree (e.g. a second FadeStackedWidget).
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation
