import sys
from PyQt6.QtWidgets import QApplication

from core.archive_service import ArchiveService
from core.password_service import PasswordService
from infrastructure.zip_repository import ZipRepository
from infrastructure.config_repository import ConfigRepository
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # macOS стиль
    app.setStyle("Fusion")

    app.setStyleSheet("""
    QMainWindow {
        background-color: #f5f5f7;
    }

    QToolBar {
        background: white;
        border-bottom: 1px solid #ddd;
    }

    QTreeWidget {
        background: white;
        border: none;
    }
    """)

    # зависимости
    password_repo = ConfigRepository("passwords.json")
    password_service = PasswordService(password_repo)

    zip_repo = ZipRepository()
    archive_service = ArchiveService(zip_repo, password_service)

    window = MainWindow(archive_service)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()