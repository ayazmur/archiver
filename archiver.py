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
from dataclasses import dataclass

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QPlainTextEdit, QVBoxLayout, QWidget, QFrame,
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
    background: #101827;
    color: #e7eefb;
    font-family: "Segoe UI";
    font-size: 14px;
}
QMainWindow { background: #101827; }
QFrame#hero, QFrame#card {
    background: #182338;
    border: 1px solid #263651;
    border-radius: 16px;
}
QLabel#eyebrow { color: #7dd3fc; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#title { color: #f8fafc; font-size: 26px; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #9fb0c9; }
QLabel#sectionTitle { color: #f1f5f9; font-size: 16px; font-weight: 700; }
QPushButton {
    background: #24334c;
    border: 1px solid #344967;
    border-radius: 9px;
    color: #e7eefb;
    min-height: 22px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover { background: #304362; border-color: #4f78a9; }
QPushButton:pressed { background: #1c2a40; }
QPushButton#primary { background: #2563eb; border-color: #3b82f6; color: white; }
QPushButton#primary:hover { background: #3574ed; }
QPushButton#danger { color: #fecaca; }
QLineEdit, QListWidget, QPlainTextEdit {
    background: #101827;
    border: 1px solid #2b3d5a;
    border-radius: 9px;
    padding: 8px;
    selection-background-color: #2563eb;
}
QListWidget::item { padding: 8px; border-radius: 6px; }
QListWidget::item:selected { background: #1d4ed8; color: white; }
QPlainTextEdit { color: #bbcae0; font-family: "Cascadia Mono", Consolas, monospace; font-size: 12px; }
QDialog { background: #182338; }
QMessageBox QPushButton { min-width: 90px; }
QScrollBar:vertical { background: #101827; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: #3a4c68; border-radius: 5px; min-height: 30px; }
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = PasswordStore()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource_path("assets/app.ico")))
        self.resize(920, 680)
        self.setMinimumSize(760, 570)
        self._build_ui()
        try:
            self.store.load()
        except RuntimeError as error:
            QMessageBox.warning(self, "База паролей", str(error))
        self.refresh_passwords()

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        hero = QFrame(); hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero); hero_layout.setContentsMargins(22, 18, 22, 18)
        title_block = QVBoxLayout()
        eyebrow = QLabel("ZIP · AES · ЛОКАЛЬНОЕ ХРАНИЛИЩЕ"); eyebrow.setObjectName("eyebrow")
        title = QLabel("Архиватор"); title.setObjectName("title")
        subtitle = QLabel("Создавайте и распаковывайте защищённые ZIP-архивы без лишней сложности."); subtitle.setObjectName("subtitle")
        title_block.addWidget(eyebrow); title_block.addWidget(title); title_block.addWidget(subtitle)
        hero_layout.addLayout(title_block); hero_layout.addStretch()
        self.status = QLabel("Готов к работе"); self.status.setObjectName("hint")
        hero_layout.addWidget(self.status, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(hero)

        actions = QHBoxLayout(); actions.setSpacing(12)
        extract = QPushButton("↧  Распаковать архив"); extract.setObjectName("primary")
        create = QPushButton("＋  Создать ZIP-архив")
        extract.clicked.connect(self.extract_archive); create.clicked.connect(self.create_archive)
        actions.addWidget(extract); actions.addWidget(create); actions.addStretch()
        layout.addLayout(actions)

        passwords_card = QFrame(); passwords_card.setObjectName("card")
        passwords_layout = QVBoxLayout(passwords_card); passwords_layout.setContentsMargins(18, 16, 18, 16)
        passwords_layout.setSpacing(10)
        header = QHBoxLayout()
        section_title = QLabel("База паролей"); section_title.setObjectName("sectionTitle")
        hint = QLabel("Пароли скрыты и проверяются автоматически при распаковке."); hint.setObjectName("hint")
        header.addWidget(section_title); header.addWidget(hint); header.addStretch()
        passwords_layout.addLayout(header)
        row = QHBoxLayout(); row.setSpacing(12)
        self.passwords = QListWidget(); self.passwords.setToolTip("Пароли не показываются в списке.")
        row.addWidget(self.passwords, 1)
        buttons = QVBoxLayout(); buttons.setSpacing(8)
        for text, slot, name in [("＋  Добавить", self.add_password, "primary"), ("Изменить", self.edit_password, ""), ("Удалить", self.remove_password, "danger")]:
            button = QPushButton(text); button.clicked.connect(slot)
            if name: button.setObjectName(name)
            buttons.addWidget(button)
        buttons.addStretch(); row.addLayout(buttons)
        passwords_layout.addLayout(row, 1)
        layout.addWidget(passwords_card, 1)

        log_card = QFrame(); log_card.setObjectName("card")
        log_layout = QVBoxLayout(log_card); log_layout.setContentsMargins(18, 14, 18, 14)
        journal = QLabel("Журнал операций"); journal.setObjectName("sectionTitle")
        log_layout.addWidget(journal)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(300)
        self.log.setPlaceholderText("Здесь будут отображаться выполненные операции.")
        self.log.setFixedHeight(118)
        log_layout.addWidget(self.log)
        layout.addWidget(log_card)

    def write_log(self, text: str):
        self.log.appendPlainText(text)
        self.status.setText(text)

    def refresh_passwords(self):
        self.passwords.clear()
        for item in self.store.entries:
            self.passwords.addItem(f"{item.title}   •   {'•' * min(max(len(item.password), 1), 12)}")

    def add_password(self):
        dialog = PasswordDialog(self)
        if dialog.exec_() and dialog.password.text():
            self.store.entries.append(dialog.value()); self.store.save(); self.refresh_passwords()

    def edit_password(self):
        index = self.passwords.currentRow()
        if index < 0: return
        dialog = PasswordDialog(self, self.store.entries[index])
        if dialog.exec_() and dialog.password.text():
            self.store.entries[index] = dialog.value(); self.store.save(); self.refresh_passwords()

    def remove_password(self):
        index = self.passwords.currentRow()
        if index < 0: return
        if QMessageBox.question(self, "Удалить", "Удалить выбранный пароль?") == QMessageBox.Yes:
            del self.store.entries[index]; self.store.save(); self.refresh_passwords()

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
                    raise FileExistsError(f"Уже существует: {target.name}")
                shutil.move(str(source), str(target))
        return True

    def extract_archive(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Выберите ZIP-архив", "", "ZIP (*.zip)")
        if not filename: return
        archive = Path(filename)
        destination = QFileDialog.getExistingDirectory(self, "Папка для распаковки", str(archive.parent))
        if not destination: return
        destination_path = Path(destination)
        self.write_log(f"Открываю: {archive.name}")
        # Сначала пробуем базу. None означает попытку открыть незащищённый архив.
        attempts: list[tuple[str, str | None]] = [("без пароля", None)] + [(e.title, e.password) for e in self.store.entries]
        for title, password in attempts:
            QApplication.processEvents()
            try:
                success = self._try_extract(archive, destination_path, password)
            except FileExistsError as error:
                QMessageBox.warning(self, "Файлы уже есть", str(error)); return
            if success:
                self.write_log(f"Готово. Использован вариант: {title}")
                QMessageBox.information(self, "Готово", f"Архив распакован.\nИспользован вариант: {title}")
                return
        password, ok = QInputDialog.getText(self, "Нужен пароль", "Пароль не найден в базе. Введите пароль:", QLineEdit.Password)
        if ok and password:
            try:
                success = self._try_extract(archive, destination_path, password)
            except FileExistsError as error:
                QMessageBox.warning(self, "Файлы уже есть", str(error)); return
            if success:
                self.write_log("Готово. Использован введённый пароль.")
                if QMessageBox.question(self, "Добавить в базу", "Сохранить этот пароль в базу?") == QMessageBox.Yes:
                    title, accepted = QInputDialog.getText(self, "Название", "Например: Поставщик А")
                    if accepted:
                        self.store.entries.append(PasswordEntry(title or "Без названия", password)); self.store.save(); self.refresh_passwords()
                return
        self.write_log("Архив не распакован: пароль не подошёл или операция отменена.")
        QMessageBox.warning(self, "Не удалось распаковать", "Не удалось открыть архив с указанными паролями.")

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
            self.write_log(f"Создан архив: {filename}")
            QMessageBox.information(self, "Готово", "Архив создан.")
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать архив:\n{error}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(QIcon(resource_path("assets/app.ico")))
    window = MainWindow(); window.show()
    sys.exit(app.exec_())
