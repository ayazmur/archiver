# gui_archiver.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sqlite3
import zipfile
import threading
import sys

# --- Настройки ---
DB_NAME = "passwords.db"


# --- БЭКЕНД: Логика работы с БД и архивами (немного изменена для GUI) ---
# Функции теперь не печатают в консоль, а возвращают результат или вызывают колбэки.

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


def delete_password_from_db(password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM passwords WHERE password = ?", (password,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def create_archive_logic(source_path, archive_name, password, log_callback):
    try:
        log_callback(f"Начинаю создание архива '{archive_name}'...")
        with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zf:
            if password:
                zf.setpassword(password.encode('utf-8'))

            if os.path.isdir(source_path):
                for root, _, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=source_path)
                        zf.write(file_path, arcname)
                        log_callback(f"Добавлен: {arcname}")
            else:
                zf.write(source_path, os.path.basename(source_path))
                log_callback(f"Добавлен: {os.path.basename(source_path)}")

        log_callback("Архив успешно создан.")
        if password:
            log_callback(add_password_to_db(password))
    except Exception as e:
        log_callback(f"Ошибка при создании архива: {e}")


def extract_archive_logic(archive_name, dest_path, log_callback, ask_password_callback, ask_save_password_callback):
    try:
        log_callback(f"Начинаю распаковку '{archive_name}' в '{dest_path}'...")
        with zipfile.ZipFile(archive_name, 'r') as zf:
            try:
                # Пробуем без пароля
                zf.extractall(path=dest_path)
                log_callback("Архив успешно распакован (без пароля).")
                return
            except RuntimeError:  # Ожидаем ошибку "password required"
                pass  # Продолжаем, чтобы попробовать с паролем

            log_callback("Архив защищен паролем. Пробую пароли из базы...")
            passwords_to_try = get_passwords_from_db()
            for pwd in passwords_to_try:
                try:
                    zf.extractall(path=dest_path, pwd=pwd.encode('utf-8'))
                    log_callback(f"УСПЕХ! Распаковано с паролем из базы: '{pwd}'")
                    return
                except (RuntimeError, zipfile.BadZipFile):
                    continue

            log_callback("Пароли из базы не подошли.")
            while True:
                manual_pwd = ask_password_callback()
                if not manual_pwd:
                    log_callback("Распаковка отменена пользователем.")
                    return
                try:
                    zf.extractall(path=dest_path, pwd=manual_pwd.encode('utf-8'))
                    log_callback("Успешно распаковано с введенным паролем.")
                    if ask_save_password_callback(manual_pwd):
                        log_callback(add_password_to_db(manual_pwd))
                    return
                except (RuntimeError, zipfile.BadZipFile):
                    log_callback("Неверный пароль. Попробуйте еще раз.")
                    if not messagebox.askretrycancel("Неверный пароль", "Пароль не подошел. Попробовать еще раз?"):
                        log_callback("Распаковка отменена.")
                        return

    except Exception as e:
        log_callback(f"Ошибка при распаковке: {e}")


# --- ФРОНТЕНД: GUI на Tkinter ---

class ArchiverApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GUI Архиватор")
        self.geometry("700x500")

        # Создаем вкладки
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        # Создаем сами фреймы-вкладки
        self.create_tab = ttk.Frame(self.notebook)
        self.extract_tab = ttk.Frame(self.notebook)
        self.pass_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.create_tab, text="Архивация")
        self.notebook.add(self.extract_tab, text="Распаковка")
        self.notebook.add(self.pass_tab, text="Пароли")

        # Лог для вывода информации
        self.log_frame = ttk.Frame(self)
        self.log_frame.pack(padx=10, pady=5, fill="x")
        self.log_text = tk.Text(self.log_frame, height=8, state="disabled")
        self.log_text.pack(side="left", fill="x", expand=True)
        scrollbar = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Наполняем каждую вкладку
        self.setup_create_tab()
        self.setup_extract_tab()
        self.setup_pass_tab()

        init_db()
        self.log("Приложение запущено. База данных готова.")
        self.update_passwords_list()

        # Обработка файла, переданного в командной строке
        if len(sys.argv) > 1:
            self.handle_cmd_argument(sys.argv[1])

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)  # автопрокрутка
        self.log_text.config(state="disabled")

    def run_in_thread(self, target_func, *args):
        # Запускает функцию в отдельном потоке, чтобы не блокировать GUI
        thread = threading.Thread(target=target_func, args=args)
        thread.daemon = True
        thread.start()

    # --- Вкладка Архивация ---
    def setup_create_tab(self):
        frame = self.create_tab
        ttk.Label(frame, text="Исходный файл/папка:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.create_source_entry = ttk.Entry(frame, width=50)
        self.create_source_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(frame, text="Выбрать...", command=self.select_source_for_create).grid(row=0, column=2, padx=5,
                                                                                         pady=5)

        ttk.Label(frame, text="Имя архива:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.create_archive_entry = ttk.Entry(frame, width=50)
        self.create_archive_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(frame, text="Сохранить как...", command=self.select_archive_for_create).grid(row=1, column=2, padx=5,
                                                                                                pady=5)

        self.use_password_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Использовать пароль", variable=self.use_password_var,
                        command=self.toggle_password_entry).grid(row=2, column=0, padx=5, pady=5)
        self.create_password_entry = ttk.Entry(frame, show="*", state="disabled")
        self.create_password_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ttk.Button(frame, text="Создать архив", command=self.handle_create_archive).grid(row=3, column=1, pady=20)
        frame.columnconfigure(1, weight=1)

    def select_source_for_create(self):
        path = filedialog.askopenfilename() or filedialog.askdirectory()
        if path:
            self.create_source_entry.delete(0, tk.END)
            self.create_source_entry.insert(0, path)

    def select_archive_for_create(self):
        path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP archives", "*.zip")])
        if path:
            self.create_archive_entry.delete(0, tk.END)
            self.create_archive_entry.insert(0, path)

    def toggle_password_entry(self):
        self.create_password_entry.config(state="normal" if self.use_password_var.get() else "disabled")

    def handle_create_archive(self):
        source = self.create_source_entry.get()
        archive = self.create_archive_entry.get()
        password = self.create_password_entry.get() if self.use_password_var.get() else None
        if not source or not archive:
            messagebox.showerror("Ошибка", "Необходимо указать источник и имя архива!")
            return
        self.run_in_thread(create_archive_logic, source, archive, password, self.log)

    # --- Вкладка Распаковка ---
    def setup_extract_tab(self):
        frame = self.extract_tab
        ttk.Label(frame, text="Архив для распаковки:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.extract_source_entry = ttk.Entry(frame, width=50)
        self.extract_source_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(frame, text="Выбрать...", command=self.select_source_for_extract).grid(row=0, column=2, padx=5,
                                                                                          pady=5)

        ttk.Label(frame, text="Папка назначения:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.extract_dest_entry = ttk.Entry(frame, width=50)
        self.extract_dest_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(frame, text="Выбрать...", command=self.select_dest_for_extract).grid(row=1, column=2, padx=5, pady=5)
        # Установить текущую папку по умолчанию
        self.extract_dest_entry.insert(0, os.getcwd())

        ttk.Button(frame, text="Извлечь", command=self.handle_extract_archive).grid(row=2, column=1, pady=20)
        frame.columnconfigure(1, weight=1)

    def select_source_for_extract(self):
        path = filedialog.askopenfilename(filetypes=[("ZIP archives", "*.zip")])
        if path:
            self.extract_source_entry.delete(0, tk.END)
            self.extract_source_entry.insert(0, path)

    def select_dest_for_extract(self):
        path = filedialog.askdirectory()
        if path:
            self.extract_dest_entry.delete(0, tk.END)
            self.extract_dest_entry.insert(0, path)

    def ask_password_from_gui(self):
        return simpledialog.askstring("Пароль", "Введите пароль для архива:", show='*')

    def ask_save_password_from_gui(self, password):
        return messagebox.askyesno("Сохранить пароль?", f"Хотите сохранить пароль '{password}' в базу?")

    def handle_extract_archive(self):
        source = self.extract_source_entry.get()
        dest = self.extract_dest_entry.get()
        if not source or not dest:
            messagebox.showerror("Ошибка", "Необходимо указать архив и папку назначения!")
            return
        self.run_in_thread(extract_archive_logic, source, dest, self.log, self.ask_password_from_gui,
                           self.ask_save_password_from_gui)

    def handle_cmd_argument(self, filepath):
        self.log(f"Открыт файл: {filepath}")
        self.notebook.select(self.extract_tab)  # Переключаемся на вкладку распаковки
        self.extract_source_entry.delete(0, tk.END)
        self.extract_source_entry.insert(0, filepath)

    # --- Вкладка Пароли ---
    def setup_pass_tab(self):
        frame = self.pass_tab
        # Список паролей
        list_frame = ttk.Frame(frame)
        list_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.pass_listbox = tk.Listbox(list_frame)
        self.pass_listbox.pack(side="left", fill="both", expand=True)
        list_scrollbar = ttk.Scrollbar(list_frame, command=self.pass_listbox.yview)
        list_scrollbar.pack(side="right", fill="y")
        self.pass_listbox.config(yscrollcommand=list_scrollbar.set)

        # Кнопки управления
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Удалить выбранный", command=self.handle_delete_password).pack(side="left", padx=5)

        # Добавление нового пароля
        add_frame = ttk.Frame(frame)
        add_frame.pack(pady=5, fill="x", padx=10)
        self.pass_add_entry = ttk.Entry(add_frame)
        self.pass_add_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(add_frame, text="Добавить пароль", command=self.handle_add_password).pack(side="left")

    def update_passwords_list(self):
        self.pass_listbox.delete(0, tk.END)
        for pwd in get_passwords_from_db():
            self.pass_listbox.insert(tk.END, pwd)

    def handle_delete_password(self):
        selected_indices = self.pass_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("Внимание", "Выберите пароль для удаления.")
            return

        password = self.pass_listbox.get(selected_indices[0])
        if messagebox.askyesno("Подтверждение", f"Вы уверены, что хотите удалить пароль '{password}'?"):
            if delete_password_from_db(password):
                self.log(f"Пароль '{password}' удален.")
                self.update_passwords_list()
            else:
                self.log(f"Не удалось удалить пароль '{password}'.")

    def handle_add_password(self):
        password = self.pass_add_entry.get()
        if password:
            result = add_password_to_db(password)
            self.log(result)
            self.pass_add_entry.delete(0, tk.END)
            self.update_passwords_list()
        else:
            messagebox.showwarning("Внимание", "Поле пароля не может быть пустым.")


if __name__ == "__main__":
    app = ArchiverApp()
    app.mainloop()