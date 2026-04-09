from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QToolBar, QMessageBox, QApplication, QStatusBar
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject

from ui.dialogs.password_dialog import PasswordDialog
from ui.dialogs.password_manager_dialog import PasswordManagerDialog
from core.update_service import UpdateService

import webbrowser
import os


# --- Worker для фоновых задач ---
class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


# --- Main Window ---
class MainWindow(QMainWindow):
    # ИСПРАВЛЕНО: добавлена поддержка двух сервисов в аргументах
    def __init__(self, archive_service, password_service):
        super().__init__()

        self.archive_service = archive_service
        self.password_service = password_service  # Сохраняем сервис паролей

        self.archive_path = None
        self.threadpool = QThreadPool()
        self.update_service = UpdateService("YOUR_USERNAME/YOUR_REPO")

        self.setWindowTitle("Modern Archiver")
        self.resize(1000, 650)

        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        self.setup_toolbar()
        self.setup_tree()
        self.setup_statusbar()

    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Открыть
        open_action = QAction("📂 Open", self)
        open_action.triggered.connect(self.open_archive)
        toolbar.addAction(open_action)

        # Извлечь
        extract_action = QAction("📦 Extract", self)
        extract_action.triggered.connect(self.extract_archive)
        toolbar.addAction(extract_action)

        # Управление паролями
        passwords_action = QAction("🔑 Passwords", self)
        passwords_action.triggered.connect(self.manage_passwords)
        toolbar.addAction(passwords_action)

        toolbar.addSeparator()

        # Обновление
        update_action = QAction("🔄 Check Updates", self)
        update_action.triggered.connect(self.check_updates)
        toolbar.addAction(update_action)

        # Выход
        exit_action = QAction("❌ Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        toolbar.addAction(exit_action)

    def setup_tree(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.setColumnWidth(0, 500)
        self.tree.setAlternatingRowColors(True)
        self.setCentralWidget(self.tree)

    def setup_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def apply_styles(self):
        self.setStyleSheet("""
        QMainWindow { background-color: #f5f5f7; }
        QToolBar { background: white; border-bottom: 1px solid #ddd; spacing: 6px; padding: 6px; }
        QTreeWidget { background: white; border: none; font-size: 13px; }
        QStatusBar { background: #fafafa; border-top: 1px solid #ddd; }
        """)

    def open_archive(self):
        formats = self.archive_service.get_supported_formats()
        filter_str = "Archives (" + " ".join([f"*{f}" for f in formats]) + ");;All files (*.*)"

        path, _ = QFileDialog.getOpenFileName(self, "Open Archive", "", filter_str)
        if not path: return

        self.archive_path = path
        self.setWindowTitle(f"Modern Archiver - {os.path.basename(path)}")

        worker = Worker(lambda: self.archive_service.list_files(path))
        worker.signals.finished.connect(self.on_archive_loaded)
        worker.signals.error.connect(lambda m: QMessageBox.critical(self, "Error", m))

        self.threadpool.start(worker)
        self.status.showMessage("Loading...")

    def on_archive_loaded(self, files):
        self.tree.clear()
        for f in files:
            size_txt = f"{f['size'] / 1024:.1f} KB" if f['size'] > 0 else ("Folder" if f['is_dir'] else "0 B")
            self.tree.addTopLevelItem(QTreeWidgetItem([f["name"], size_txt]))
        self.status.showMessage(f"Loaded {len(files)} items")

    def extract_archive(self):
        if not self.archive_path:
            QMessageBox.warning(self, "Warning", "Open archive first")
            return

        dest = QFileDialog.getExistingDirectory(self, "Select Destination")
        if not dest: return

        worker = Worker(lambda: self.archive_service.extract_all(
            self.archive_path, dest, lambda: PasswordDialog.ask(self)
        ))
        worker.signals.finished.connect(self.on_extract_done)
        self.threadpool.start(worker)
        self.status.showMessage("Extracting...")

    def on_extract_done(self, success):
        msg = "Extraction completed" if success else "Extraction failed"
        QMessageBox.information(self, "Result", msg)
        self.status.showMessage("Ready")

    def manage_passwords(self):
        # ИСПРАВЛЕНО: теперь self.password_service гарантированно передан
        dialog = PasswordManagerDialog(self.password_service, self)
        dialog.exec()

    def check_updates(self):
        worker = Worker(self.update_service.check_update)
        worker.signals.finished.connect(self.on_update_checked)
        self.threadpool.start(worker)

    def on_update_checked(self, info):
        if not info:
            QMessageBox.information(self, "Update", "Up to date")
            return
        if QMessageBox.question(self, "Update",
                                f"New version {info['version']} available. Download?") == QMessageBox.StandardButton.Yes:
            webbrowser.open(info["download"])