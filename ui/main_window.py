from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QTreeWidget,
    QTreeWidgetItem, QToolBar, QMessageBox
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from ui.dialogs.password_dialog import PasswordDialog


class MainWindow(QMainWindow):
    def __init__(self, archive_service):
        super().__init__()

        self.archive_service = archive_service
        self.archive_path = None

        self.setWindowTitle("Modern Archiver")
        self.resize(900, 600)

        self.setup_ui()

    def setup_ui(self):
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        open_action = QAction("📂 Open", self)
        open_action.triggered.connect(self.open_archive)
        toolbar.addAction(open_action)

        extract_action = QAction("📦 Extract", self)
        extract_action.triggered.connect(self.extract_archive)
        toolbar.addAction(extract_action)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size"])
        self.setCentralWidget(self.tree)

    def open_archive(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open ZIP", "", "ZIP (*.zip)")
        if not path:
            return

        self.archive_path = path
        self.tree.clear()

        try:
            files = self.archive_service.list_files(path)

            for f in files:
                size = f"{f['size'] / 1024:.1f} KB"
                item = QTreeWidgetItem([f["name"], size])
                self.tree.addTopLevelItem(item)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def extract_archive(self):
        if not self.archive_path:
            return

        dest = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not dest:
            return

        success = self.archive_service.extract_all(
            self.archive_path,
            dest,
            lambda: PasswordDialog.ask(self)
        )

        if success:
            QMessageBox.information(self, "Done", "Extracted successfully")
        else:
            QMessageBox.warning(self, "Error", "Extraction failed")