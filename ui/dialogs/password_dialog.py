from PyQt6.QtWidgets import QInputDialog


class PasswordDialog:
    @staticmethod
    def ask(parent=None):
        text, ok = QInputDialog.getText(
            parent,
            "Password",
            "Enter password:",
        )
        return text if ok else None