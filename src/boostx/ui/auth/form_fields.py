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
    # Stashed here (rather than returning a tuple) so callers that only need
    # the field for its value can retranslate the label later via field.label.
    field.label = label
    return field
