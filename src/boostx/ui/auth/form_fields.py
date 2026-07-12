from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget


def add_field(layout: QVBoxLayout, parent: QWidget, label_text: str, *, is_password: bool = False) -> QLineEdit:
    label = QLabel(label_text, parent)
    label.setObjectName("AuthFieldLabel")
    field = QLineEdit(parent)
    field.setFixedHeight(36)
    if is_password:
        field.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(label)
    layout.addWidget(field)
    return field
