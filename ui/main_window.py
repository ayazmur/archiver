from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QToolBar, QMessageBox, QApplication, QStatusBar
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject

from ui.dialogs.password_dialog import PasswordDialog
from core.update_service import UpdateService

import webbrowser
import os


# ---------- Worker для потоков ----------
class WorkerSignals(QObject):
    finished = pyqtSignal(bool)
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


# ---------- Main Window ----------
class MainWindow(QMainWindow):
    def __init__(self, archive_service):
        super().__init__()

        self.archive_service = archive_service
        self.archive_path = None

        self.threadpool = QThreadPool()

        self.update_service = UpdateService("YOUR_USERNAME/YOUR_REPO")

        self.setWindowTitle("Modern Archiver")
        self.resize(1000, 650)

        self.setup_ui()
        self.apply_styles()

    # ---------- UI ----------
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
        self.set_status("Ready")

    # ---------- STYLE ----------
    def apply_styles(self):
        self.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f7;
        }

        QToolBar {
            background: white;
            border-bottom: 1px solid #ddd;
            spacing: 6px;
            padding: 6px;
        }

        QTreeWidget {
            background: white;
            border: none;
            font-size: 13px;
        }

        QStatusBar {
            background: #fafafa;
            border-top: 1px solid #ddd;
        }
        """)

    # ---------- STATUS ----------
    def set_status(self, text):
        self.status.showMessage(text)

    # ---------- OPEN ----------
    def open_archive(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ZIP",
            "",
            "ZIP (*.zip)"
        )

        if not path:
            return

        self.archive_path = path
        self.setWindowTitle(f"Modern Archiver - {os.path.basename(path)}")
        self.tree.clear()

        def task():
            return self.archive_service.list_files(path)

        worker = Worker(task)
        worker.signals.finished.connect(self.on_archive_loaded)
        worker.signals.error.connect(self.show_error)

        self.threadpool.start(worker)
        self.set_status("Loading archive...")

    def on_archive_loaded(self, files):
        self.tree.clear()

        for f in files:
            size = f"{f['size'] / 1024:.1f} KB"
            item = QTreeWidgetItem([f["name"], size])
            self.tree.addTopLevelItem(item)

        self.set_status("Archive loaded")

    # ---------- EXTRACT ----------
    def extract_archive(self):
        if not self.archive_path:
            QMessageBox.warning(self, "Warning", "Open archive first")
            return

        dest = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not dest:
            return

        def task():
            return self.archive_service.extract_all(
                self.archive_path,
                dest,
                lambda: PasswordDialog.ask(self)
            )

        worker = Worker(task)
        worker.signals.finished.connect(self.on_extract_done)
        worker.signals.error.connect(self.show_error)

        self.threadpool.start(worker)
        self.set_status("Extracting...")

    def on_extract_done(self, success):
        if success:
            QMessageBox.information(self, "Done", "Extraction completed")
            self.set_status("Done")
        else:
            QMessageBox.warning(self, "Error", "Extraction failed")
            self.set_status("Error")

    # ---------- UPDATE ----------
    def check_updates(self):
        self.set_status("Checking updates...")

        def task():
            return self.update_service.check_update()

        worker = Worker(task)
        worker.signals.finished.connect(self.on_update_checked)
        worker.signals.error.connect(self.show_error)

        self.threadpool.start(worker)

    def on_update_checked(self, info):
        self.set_status("Ready")

        if not info:
            QMessageBox.information(self, "Update", "No updates found")
            return

        reply = QMessageBox.question(
            self,
            "Update available",
            f"Version {info['version']} available.\nDownload?"
        )

        if reply == QMessageBox.StandardButton.Yes:
            webbrowser.open(info["download"])

    # ---------- ERROR ----------
    def show_error(self, msg):
        QMessageBox.critical(self, "Error", msg)
        self.set_status("Error")