"""Архиватор ZIP с локальной базой паролей (Windows / PyQt5)."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QStatusBar, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
import pyzipper


APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "PasswordArchiver"
DB_PATH = APP_DIR / "passwords.dat"
APP_NAME = "Архиватор"


def resource_path(relative: str) -> str:
    """Возвращает путь к файлу как в исходниках, так и внутри PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / relative)


APP_STYLE = """
QWidget {
    background: #f0f0f0;
    color: #1c2534;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow { background: #f0f0f0; }
QMenuBar { background: #f0f0f0; }
QMenuBar::item:selected { background: #cfe4ff; }
QMenu {
    background: #fafafa;
    border: 1px solid #b8c2cf;
}
QMenu::item:selected { background: #cfe4ff; }
QToolBar { background: #f0f0f0; border: none; spacing: 2px; padding: 2px; }
QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}
QToolBar QToolButton:hover { background: #dceafc; border-color: #9cc3ef; }
QToolBar QToolButton:pressed { background: #c8ddf6; }
QComboBox, QLineEdit, QListWidget, QTreeWidget {
    background: #ffffff;
    border: 1px solid #b8c2cf;
    border-radius: 4px;
    padding: 4px;
    color: #1c2534;
    selection-background-color: #2f6fd0;
    selection-color: #ffffff;
}
QLineEdit#addressBar { color: #4a5568; }
QTreeWidget {
    border: 1px solid #b8c2cf;
    border-radius: 4px;
    gridlines-color: #dde3ea;
}
QTreeWidget::item { padding: 3px; }
QTreeWidget::item:selected { background: #2f6fd0; color: #ffffff; }
QHeaderView::section {
    background: #eef2f7;
    border: none;
    border-right: 1px solid #d5dbe3;
    border-bottom: 1px solid #d5dbe3;
    padding: 4px;
    font-weight: 600;
}
QListWidget::item { padding: 5px; border-radius: 4px; }
QListWidget::item:selected { background: #2f6fd0; color: white; }
QPushButton {
    background: #e8edf4;
    border: 1px solid #b8c2cf;
    border-radius: 6px;
    color: #1c2534;
    min-height: 20px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover { background: #dceafc; border-color: #9cc3ef; }
QPushButton:pressed { background: #c8ddf6; }
QPushButton#primary { background: #2563eb; border-color: #3b82f6; color: white; }
QPushButton#primary:hover { background: #3574ed; }
QPushButton#danger { color: #b91c1c; }
QStatusBar { background: #e8edf4; color: #4a5568; }
QDialog { background: #f0f0f0; }
QMessageBox QPushButton { min-width: 90px; }
QScrollBar:vertical { background: #f0f0f0; width: 12px; }
QScrollBar::handle:vertical { background: #c3ccd8; border-radius: 6px; min-height: 30px; }
QScrollBar:horizontal { background: #f0f0f0; height: 12px; }
QScrollBar::handle:horizontal { background: #c3ccd8; border-radius: 6px; min-width: 30px; }
"""


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect(data: bytes) -> bytes:
    """Шифрует данные ключом текущей учётной записи Windows (DPAPI)."""
    if os.name != "nt":
        raise OSError("Для защищённой базы паролей требуется Windows.")
    source, source_buffer = _blob(data)
    target = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "Password Archiver", None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _unprotect(data: bytes) -> bytes:
    source, source_buffer = _blob(data)
    target = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


@dataclass
class PasswordEntry:
    title: str
    password: str


class PasswordStore:
    def __init__(self):
        self.entries: list[PasswordEntry] = []

    def load(self):
        if not DB_PATH.exists():
            return
        try:
            payload = _unprotect(base64.b64decode(DB_PATH.read_bytes()))
            self.entries = [PasswordEntry(**item) for item in json.loads(payload)]
        except Exception as error:
            raise RuntimeError("Не удалось открыть базу паролей. Возможно, она создана другой учётной записью.") from error

    def save(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        raw = json.dumps([entry.__dict__ for entry in self.entries], ensure_ascii=False).encode("utf-8")
        DB_PATH.write_bytes(base64.b64encode(_protect(raw)))


def _human_size(value: int) -> str:
    size = float(value)
    for unit in ("КБ", "МБ", "ГБ"):
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}" if size != int(size) else f"{int(size)} {unit}"
    return f"{size:.1f} ТБ"


class PasswordDialog(QDialog):
    def __init__(self, parent=None, entry: PasswordEntry | None = None):
        super().__init__(parent)
        self.setWindowTitle("Пароль · Архиватор")
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self.title = QLineEdit(entry.title if entry else "")
        self.password = QLineEdit(entry.password if entry else "")
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow("Название:", self.title)
        form.addRow("Пароль:", self.password)
        buttons = QHBoxLayout()
        ok, cancel = QPushButton("Сохранить"), QPushButton("Отмена")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        buttons.addWidget(ok); buttons.addWidget(cancel)
        form.addRow(buttons)

    def value(self) -> PasswordEntry:
        return PasswordEntry(self.title.text().strip() or "Без названия", self.password.text())


class PasswordBaseDialog(QDialog):
    """Отдельное окно базы паролей (аналог «Сейва» в менеджере паролей)."""

    def __init__(self, store: PasswordStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("База паролей · Архиватор")
        self.resize(480, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QLabel("База паролей")
        header.setStyleSheet("font-weight: 700; font-size: 15px;")
        hint = QLabel("Пароли скрыты и проверяются автоматически при распаковке.")
        hint.setObjectName("hint")
        header_hint = QVBoxLayout()
        header_hint.addWidget(header)
        header_hint.addWidget(hint)
        layout.addLayout(header_hint)

        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setToolTip("Пароли не показываются в списке.")
        row.addWidget(self.list, 1)
        buttons = QVBoxLayout(); buttons.setSpacing(8)
        for text, slot, name in [("＋  Добавить", self.add, "primary"), ("Изменить", self.edit, ""), ("Удалить", self.remove, "danger")]:
            button = QPushButton(text); button.clicked.connect(slot)
            if name: button.setObjectName(name)
            buttons.addWidget(button)
        buttons.addStretch(); row.addLayout(buttons)
        layout.addLayout(row, 1)

        self.refresh()

    def refresh(self):
        self.list.clear()
        for entry in self.store.entries:
            self.list.addItem(f"{entry.title}   •   {'•' * min(max(len(entry.password), 1), 12)}")

    def _selected(self) -> int:
        return self.list.currentRow()

    def add(self):
        dialog = PasswordDialog(self)
        if dialog.exec_() and dialog.password.text():
            self.store.entries.append(dialog.value()); self.store.save(); self.refresh()

    def edit(self):
        index = self._selected()
        if index < 0: return
        dialog = PasswordDialog(self, self.store.entries[index])
        if dialog.exec_() and dialog.password.text():
            self.store.entries[index] = dialog.value(); self.store.save(); self.refresh()

    def remove(self):
        index = self._selected()
        if index < 0: return
        if QMessageBox.question(self, "Удалить", "Удалить выбранный пароль?") == QMessageBox.Yes:
            del self.store.entries[index]; self.store.save(); self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = PasswordStore()
        self.archive: Path | None = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource_path("assets/app.ico")))
        self.resize(960, 640)
        self.setMinimumSize(720, 480)
        self._build_ui()
        try:
            self.store.load()
        except RuntimeError as error:
            QMessageBox.warning(self, "База паролей", str(error))
        self.set_status("Готов к работе")

    def _build_ui(self):
        # ---- Меню (как в 7-Zip/WinRAR) ----
        file_menu = self.menuBar().addMenu("Файл")
        open_action = file_menu.addAction("Открыть… (Ctrl+O)")
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_archive_dialog)
        extract_action = file_menu.addAction("Разжать здесь (F7)")
        extract_action.setShortcut(QKeySequence("F7"))
        extract_action.triggered.connect(self.extract_current)
        create_action = file_menu.addAction("Сжать файлы…")
        create_action.triggered.connect(self.create_archive)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Выход", )
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        service_menu = self.menuBar().addMenu("Сервис")
        service_menu.addAction("База паролей…", self.show_password_base)

        # ---- Панель инструментов ----
        toolbar = QToolBar("Действия")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        b_extract = toolbar.addAction("Разжать здесь")
        b_extract.triggered.connect(self.extract_current)
        b_create = toolbar.addAction("Сжатие")
        b_create.triggered.connect(self.create_archive)
        b_open = toolbar.addAction("Открыть")
        b_open.triggered.connect(self.open_archive_dialog)
        toolbar.addSeparator()
        b_base = toolbar.addAction("База паролей")
        b_base.triggered.connect(self.show_password_base)

        # ---- Строка адреса + дерево файлов ----
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        address_row = QHBoxLayout()
        label = QLabel("Место:  ")
        self.address = QLineEdit()
        self.address.setObjectName("addressBar")
        self.address.setReadOnly(True)
        self.address.setPlaceholderText("Архив не открыт. Выберите файл через Файл → Открыть или кнопку «Открыть».")
        button_open = QPushButton("Открыть…")
        button_open.clicked.connect(self.open_archive_dialog)
        address_row.addWidget(label)
        address_row.addWidget(self.address, 1)
        address_row.addWidget(button_open)
        layout.addLayout(address_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Имя", "Тип", "Размер", "После сжатия", "Изменён"])
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(False)
        self.tree.itemDoubleClicked.connect(self._on_item_double_click)
        header = self.tree.header()
        header.setSectionResizeMode(0, header.Stretch())
        for column in (1, 2, 3, 4):
            header.setSectionResizeMode(column, header.ResizeToContents)
        layout.addWidget(self.tree, 1)

        # ---- Строка состояния ----
        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def set_status(self, text: str):
        self.status.showMessage(text)

    # ---------- Открытие и просмотр архива ----------

    def open_archive_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Открыть архив", "", "Архивы (*.zip);;Все файлы (*)")
        if filename:
            self.open_archive(Path(filename))

    def open_archive(self, path: Path):
        if not path.is_file():
            self.set_status(f"Файл не найден: {path}")
            return
        self.archive = path
        self.address.setText(str(path))
        self.tree.clear()
        try:
            with pyzipper.AESZipFile(path) as zf:
                items = zf.infolist()
        except (OSError, pyzipper.zipfile.BadZipFile) as error:
            self.archive = None
            self.set_status(f"Не удалось открыть архив: {error}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть архив:\n{error}")
            return
        added = 0
        for info in items:
            item = QTreeWidgetItem(self.tree)
            is_dir = info.is_dir()
            item.setText(0, info.filename)
            item.setText(1, "Папка" if is_dir else "Файл")
            item.setText(2, "" if is_dir else _human_size(info.file_size))
            item.setText(3, "" if is_dir else _human_size(info.compress_size))
            if is_dir:
                item.setText(4, "")
            else:
                item.setText(4, time.strftime("%d.%m.%Y %H:%M", info.date_time) if info.date_time else "")
            added += 1
        self.set_status(f"Открыт: {path.name} ({added} элементов)")
        self.setWindowTitle(f"{path.name} — {APP_NAME}")

    def _on_item_double_click(self, item: QTreeWidgetItem, _):
        """Двойной клик по файлу в архиве — извлечь во временную папку и открыть стандартным приложением."""
        if self.archive is None or item.text(1) != "Файл":
            return
        name = item.text(0)
        candidates: list[str | None] = [None] + [entry.password for entry in self.store.entries if entry.password]
        for password in candidates:
            try:
                with pyzipper.AESZipFile(self.archive) as zf:
                    if password is not None: zf.setpassword(password.encode("utf-8"))
                    data = zf.read(name)
                break
            except Exception:
                continue
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось прочитать файл из архива.\nВозможно, нужен пароль, которого нет в базе.")
            return
        extension = Path(name).suffix or ".bin"
        temp = Path(tempfile.gettempdir()) / f"archiver_{os.getpid()}{extension}"
        temp.write_bytes(data)
        os.startfile(str(temp), "open")  # type: ignore[attr-defined]

    # ---------- Распаковка ----------

    def _try_extract(self, archive: Path, destination: Path, password: str | None) -> bool:
        """Распаковывает во временную папку, чтобы неверный пароль не оставил мусор."""
        with tempfile.TemporaryDirectory(prefix="password_archiver_") as temp_name:
            temp = Path(temp_name)
            try:
                with pyzipper.AESZipFile(archive) as zf:
                    if password is not None: zf.setpassword(password.encode("utf-8"))
                    # Не позволяем архиву записать файл за пределами целевой папки (ZIP Slip).
                    for info in zf.infolist():
                        candidate = (temp / info.filename).resolve()
                        if candidate != temp.resolve() and temp.resolve() not in candidate.parents:
                            raise ValueError("Архив содержит небезопасный путь к файлу.")
                    zf.extractall(temp)
            except (RuntimeError, pyzipper.zipfile.BadZipFile, OSError, ValueError):
                return False
            destination.mkdir(parents=True, exist_ok=True)
            for source in temp.iterdir():
                target = destination / source.name
                if target.exists():
                    raise FileExistsError(f"Уже существует: {destination / target.name}")
                shutil.move(str(source), str(target))
        return True

    def extract_current(self):
        if self.archive is None or not self.archive.is_file():
            self.open_archive_dialog()
            if self.archive is None:
                return
            return
        destination = self.archive.parent
        self.set_status(f"Разжимаю: {self.archive.name} → {destination}")
        # Сначала пробуем базу. None означает попытку открыть незащищённый архив.
        attempts: list[tuple[str, str | None]] = [("без пароля", None)] + [(e.title, e.password) for e in self.store.entries]
        for title, password in attempts:
            QApplication.processEvents()
            try:
                success = self._try_extract(self.archive, destination, password)
            except FileExistsError as error:
                QMessageBox.warning(self, "Файлы уже есть", str(error)); return
            if success:
                self.set_status(f"Готово. Использован вариант: {title}")
                return
        password, ok = QInputDialog.getText(self, "Нужен пароль", "Пароль не найден в базе. Введите пароль:", QLineEdit.Password)
        if ok and password:
            try:
                success = self._try_extract(self.archive, destination, password)
            except FileExistsError as error:
                QMessageBox.warning(self, "Файлы уже есть", str(error)); return
            if success:
                self.set_status("Готово. Использован введённый пароль.")
                if QMessageBox.question(self, "Добавить в базу", "Сохранить этот пароль в базу?") == QMessageBox.Yes:
                    title, accepted = QInputDialog.getText(self, "Название", "Например: Поставщик А")
                    if accepted:
                        self.store.entries.append(PasswordEntry(title or "Без названия", password)); self.store.save()
                return
        self.set_status("Архив не распакован: пароль не подошёл или операция отменена.")
        QMessageBox.warning(self, "Не удалось распаковать", "Не удалось открыть архив с указанными паролями.")

    # ---------- Создание архива ----------

    def create_archive(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы для архива")
        if not files: return
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить архив", "archive.zip", "ZIP (*.zip)")
        if not filename: return
        if not filename.lower().endswith(".zip"): filename += ".zip"
        password, ok = QInputDialog.getText(self, "Защита архива", "Пароль (оставьте пустым для обычного ZIP):", QLineEdit.Password)
        if not ok: return
        try:
            if password:
                with pyzipper.AESZipFile(filename, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                    zf.setpassword(password.encode("utf-8"))
                    for file in files: zf.write(file, Path(file).name)
            else:
                with pyzipper.AESZipFile(filename, "w", compression=pyzipper.ZIP_DEFLATED) as zf:
                    for file in files: zf.write(file, Path(file).name)
            self.set_status(f"Создан архив: {filename}")
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать архив:\n{error}")

    # ---------- База паролей ----------

    def show_password_base(self):
        dialog = PasswordBaseDialog(self.store, self)
        dialog.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(QIcon(resource_path("assets/app.ico")))
    window = MainWindow()
    # Файл, переданный при двойном клике (ассоциация Windows): архвер.exe C:\...\file.zip
    for arg in QApplication.arguments()[1:]:
        path = Path(arg).expanduser()
        if path.is_file() and path.suffix.lower() == ".zip":
            window.open_archive(path)
            break
    window.show()
    window.raise_()
    sys.exit(app.exec_())
