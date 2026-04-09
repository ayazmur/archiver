import sys
from PyQt6.QtWidgets import QApplication
from core.archive_service import ArchiveService
from core.password_service import PasswordService
from infrastructure.zip_repository import ArchiveRepository
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Инициализация
    p_service = PasswordService()
    a_repo = ArchiveRepository()
    a_service = ArchiveService(a_repo, p_service)

    # Передаем ОБА сервиса в окно
    window = MainWindow(a_service, p_service)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()