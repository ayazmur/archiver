# modern_archiver.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sys
import threading
import zipfile
import sqlite3
from datetime import datetime

# Импортируем и применяем современную тему
import sv_ttk

# --- БЭКЕНД: Логика остаётся почти той же ---
# (Переносим сюда все функции из прошлого файла: init_db, add_password_to_db и т.д.)
# ... [Вставьте сюда все функции из раздела "БЭКЕНД" прошлого ответа] ...
# Я скопирую их сюда для полноты, чтобы файл был цельным.

DB_NAME = "passwords.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS passwords (id INTEGER PRIMARY KEY, password TEXT NOT NULL UNIQUE)")
    conn.commit()
    conn.close()


def add_password_to_db(password):
    if not password: return "Ошибка: Пустой пароль."
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO passwords (password) VALUES (?)", (password,))
        conn.commit()
        return f"Пароль '{password}' добавлен."
    except sqlite3.IntegrityError:
        return f"Пароль '{password}' уже есть в базе."
    finally:
        conn.close()


def get_passwords_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM passwords ORDER BY id")
    passwords = [row[0] for row in cursor.fetchall()]
    conn.close()
    return passwords


# ... и остальные функции бэкенда, если они есть.

def extract_archive_logic(archive_name, dest_path, log_callback, ask_password_callback, ask_save_password_callback):
    try:
        log_callback(f"Начинаю распаковку '{os.path.basename(archive_name)}'...")
        with zipfile.ZipFile(archive_name, 'r') as zf:
            try:
                zf.extractall(path=dest_path)
                log_callback("Архив успешно распакован (без пароля).")
                return True
            except RuntimeError as e:
                if "password required" not in str(e).lower():
                    raise e

            log_callback("Архив защищен паролем. Пробую пароли из базы...")
            passwords_to_try = get_passwords_from_db()
            for pwd in passwords_to_try:
                try:
                    zf.extractall(path=dest_path, pwd=pwd.encode('utf-8'))
                    log_callback(f"УСПЕХ! Распаковано с паролем из базы: '{pwd}'")
                    return True
                except (RuntimeError, zipfile.BadZipFile):
                    continue

            log_callback("Пароли из базы не подошли.")
            while True:
                manual_pwd = ask_password_callback()
                if manual_pwd is None:  # Пользователь нажал "Отмена"
                    log_callback("Распаковка отменена пользователем.")
                    return False
                try:
                    zf.extractall(path=dest_path, pwd=manual_pwd.encode('utf-8'))
                    log_callback("Успешно распаковано с введенным паролем.")
                    if ask_save_password_callback(manual_pwd):
                        log_callback(add_password_to_db(manual_pwd))
                    return True
                except (RuntimeError, zipfile.BadZipFile):
                    if not messagebox.askretrycancel("Неверный пароль", "Пароль не подошел. Попробовать еще раз?"):
                        log_callback("Распаковка отменена.")
                        return False
    except Exception as e:
        log_callback(f"Ошибка при распаковке: {e}")
        return False


# --- /БЭКЕНД ---

# --- ФРОНТЕНД: Новый GUI ---

class ArchiverApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modern Archiver")
        self.geometry("800x600")

        self.current_archive = None

        # --- Toolbar ---
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(side="top", fill="x")

        ttk.Button(toolbar, text="Открыть", command=self.open_archive).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Извлечь", command=self.show_extract_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Добавить", command=self.show_add_dialog).pack(side="left", padx=2)

        # --- File Browser (Treeview) ---
        tree_frame = ttk.Frame(self)
        tree_frame.pack(expand=True, fill="both", padx=5, pady=5)

        self.tree = ttk.Treeview(tree_frame, columns=("size", "modified", "path"), show="headings")
        self.tree.heading("size", text="Размер")
        self.tree.heading("modified", text="Дата изменения")
        self.tree.heading("path", text="Путь")

        self.tree.column("size", width=100, anchor="e")
        self.tree.column("modified", width=150, anchor="w")
        self.tree.column("path", width=400, anchor="w")

        # Добавляем Treeview в Treeview (костыль для отображения заголовка основного столбца)
        self.tree.heading("#0", text="Имя")
        self.tree.column("#0", width=200, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set)
        tree_scrollbar.pack(side="right", fill="y")

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Готово")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=5)
        status_bar.pack(side="bottom", fill="x")

        init_db()

        # Обработка файла при запуске
        if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
            self.open_archive(filepath=sys.argv[1])

    def log(self, message):
        self.status_var.set(message)
        self.update_idletasks()  # Обновляем GUI немедленно

    def run_in_thread(self, target, *args):
        threading.Thread(target=target, args=args, daemon=True).start()

    def open_archive(self, filepath=None):
        if not filepath:
            filepath = filedialog.askopenfilename(filetypes=[("ZIP archives", "*.zip")])

        if not filepath:
            return

        self.current_archive = filepath
        self.title(f"Modern Archiver - {os.path.basename(filepath)}")
        self.tree.delete(*self.tree.get_children())  # Очистить список

        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                for info in zf.infolist():
                    size = f"{info.file_size / 1024:.2f} KB"
                    modified = datetime(*info.date_time).strftime("%Y-%m-%d %H:%M:%S")
                    # Отображаем имя файла в первой колонке (#0)
                    self.tree.insert("", "end", text=os.path.basename(info.filename),
                                     values=(size, modified, info.filename))
            self.log(f"Открыт архив: {os.path.basename(filepath)}")
        except Exception as e:
            self.log(f"Ошибка открытия архива: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть архив: {e}")

    def show_extract_dialog(self):
        if not self.current_archive:
            messagebox.showwarning("Внимание", "Сначала откройте архив.")
            return

        dest_path = filedialog.askdirectory(title="Выберите папку для извлечения")
        if not dest_path:
            return

        def on_extract_done(success):
            if success:
                messagebox.showinfo("Успех", f"Файлы успешно извлечены в '{dest_path}'")
            # Если не success, то сообщения об ошибках уже были показаны

        self.run_in_thread(self.extract_archive, self.current_archive, dest_path, on_extract_done)

    def extract_archive(self, archive_path, dest_path, callback):
        # Эта функция запускается в потоке
        success = extract_archive_logic(
            archive_path, dest_path,
            log_callback=self.log,
            ask_password_callback=lambda: simpledialog.askstring("Пароль", "Введите пароль:", parent=self, show='*'),
            ask_save_password_callback=lambda pwd: messagebox.askyesno("Сохранить пароль?",
                                                                       f"Сохранить пароль '{pwd}' в базу?", parent=self)
        )
        self.after(0, callback, success)  # Вызываем колбэк в главном потоке

    def show_add_dialog(self):
        # Просто как пример - вызываем стандартный диалог
        filepath = filedialog.askopenfilename(title="Выберите файл для добавления в новый архив")
        if not filepath:
            return

        archive_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP-архивы", "*.zip")])
        if not archive_path:
            return

        password = simpledialog.askstring("Пароль", "Введите пароль (оставьте пустым, если не нужен):", show='*')

        self.log(f"Добавление {os.path.basename(filepath)} в {os.path.basename(archive_path)}...")

        # Запускаем в потоке
        self.run_in_thread(self.add_to_archive, filepath, archive_path, password)

    def add_to_archive(self, source_path, archive_path, password):
        try:
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                if password:
                    zf.setpassword(password.encode('utf-8'))

                zf.write(source_path, os.path.basename(source_path))

            self.log(f"Файл успешно добавлен в архив '{os.path.basename(archive_path)}'")
            if password:
                add_password_to_db(password)
        except Exception as e:
            self.log(f"Ошибка при добавлении в архив: {e}")


if __name__ == "__main__":
    app = ArchiverApp()

    # Устанавливаем светлую или тёмную тему в зависимости от настроек системы
    # Для Windows 10/11 это должно работать
    try:
        if tk.Tk().call("tk", "windowingsystem") == "win32":
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0:
                sv_ttk.set_theme("dark")
            else:
                sv_ttk.set_theme("light")
    except Exception:
        sv_ttk.set_theme("light")  # Тема по умолчанию, если что-то пошло не так

    app.mainloop()