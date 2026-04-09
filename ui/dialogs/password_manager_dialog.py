from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QMessageBox, QLabel
)
from PyQt6.QtCore import Qt


class PasswordManagerDialog(QDialog):
    def __init__(self, password_service, parent=None):
        super().__init__(parent)
        self.password_service = password_service
        self.setWindowTitle("Manage Passwords")
        self.setMinimumSize(400, 300)

        self.setup_ui()
        self.load_passwords()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Инструкция
        label = QLabel("Saved passwords (used for archive extraction):")
        layout.addWidget(label)

        # Список паролей
        self.password_list = QListWidget()
        self.password_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self.password_list)

        # Кнопки
        button_layout = QHBoxLayout()

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self.delete_passwords)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_all)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)

        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.clear_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def load_passwords(self):
        self.password_list.clear()
        passwords = self.password_service.get_all()

        if not passwords:
            self.password_list.addItem("No saved passwords")
        else:
            for pwd in passwords:
                # Показываем звездочки вместо реального пароля
                masked = "*" * len(pwd) if len(pwd) > 0 else ""
                self.password_list.addItem(f"{masked} (saved)")

    def delete_passwords(self):
        selected = self.password_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "Info", "Select passwords to delete")
            return

        for item in selected:
            # Получаем оригинальный пароль из сервиса
            passwords = self.password_service.get_all()
            # Простой способ - удаляем по индексу
            row = self.password_list.row(item)
            if row < len(passwords):
                self.password_service.delete(passwords[row])

        self.load_passwords()
        QMessageBox.information(self, "Success", "Passwords deleted")

    def clear_all(self):
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Delete ALL saved passwords?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.password_service.clear()
            self.load_passwords()
            QMessageBox.information(self, "Success", "All passwords cleared")