import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sys
import threading
import zipfile
import sqlite3
import tempfile
import subprocess
import time
from pathlib import Path

# Оптимизированный импорт sv_ttk с обработкой ошибок
try:
    import sv_ttk
    SV_TTK_AVAILABLE = True
except ImportError:
    SV_TTK_AVAILABLE = False

DB_NAME = "passwords.db"


# ---------- БАЗА (с кэшированием) ----------
class PasswordDB:
    """Класс для работы с БД с кэшированием"""
    _instance = None
    _cache = None
    _cache_time = 0
    _cache_duration = 5  # кэш на 5 секунд
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance
    
    def _init_db(self):
        """Инициализация БД (только один раз)"""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS passwords (id INTEGER PRIMARY KEY, password TEXT UNIQUE)")
        conn.commit()
        conn.close()
    
    def _is_cache_valid(self):
        """Проверка валидности кэша"""
        return self._cache is not None and (time.time() - self._cache_time) < self._cache_duration
    
    def add_password(self, password):
        if not password:
            return
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO passwords (password) VALUES (?)", (password,))
            conn.commit()
            self._cache = None  # инвалидируем кэш
        except:
            pass
        finally:
            conn.close()
    
    def get_passwords(self):
        """Получение паролей с кэшированием"""
        if self._is_cache_valid():
            return self._cache
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM passwords")
        data = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        self._cache = data
        self._cache_time = time.time()
        return data
    
    def delete_password(self, pwd):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM passwords WHERE password=?", (pwd,))
        conn.commit()
        conn.close()
        self._cache = None
    
    def clear_passwords(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM passwords")
        conn.commit()
        conn.close()
        self._cache = None


# Глобальный экземпляр БД
db = None


# ---------- ЛОГИКА ----------
def extract_archive_logic(archive, dest, log, ask_pwd, ask_save):
    try:
        with zipfile.ZipFile(archive, 'r') as zf:
            try:
                zf.extractall(dest)
                log("Распаковано без пароля")
                return True
            except RuntimeError:
                pass

            # пробуем базу
            for pwd in db.get_passwords():
                try:
                    zf.extractall(dest, pwd=pwd.encode())
                    log(f"Пароль найден: {pwd}")
                    return True
                except:
                    continue

            while True:
                pwd = ask_pwd()
                if not pwd:
                    return False
                try:
                    zf.extractall(dest, pwd=pwd.encode())
                    if ask_save(pwd):
                        db.add_password(pwd)
                    return True
                except:
                    if not messagebox.askretrycancel("Ошибка", "Неверный пароль"):
                        return False

    except Exception as e:
        log(str(e))
        return False


# ---------- СОЗДАНИЕ ВСТРОЕННОЙ ИКОНКИ ----------
def create_default_icon():
    """Создание простой иконки в памяти (формат ICO)"""
    # Минимальный валидный ICO файл (16x16, 32-bit)
    ico_data = bytes([
        0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x10, 0x10,
        0x00, 0x00, 0x01, 0x00, 0x20, 0x00, 0x68, 0x04,
        0x00, 0x00, 0x16, 0x00, 0x00, 0x00,  # Заглушка, реальную иконку лучше заменить
    ])
    return ico_data


# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self, archive_to_open=None):
        super().__init__()
        self.title("Modern Archiver")
        self.geometry("800x600")
        
        # Установка иконки (если есть файл)
        self.setup_icon()
        
        self.archive = None
        
        # Создание GUI (быстро)
        self.setup_ui()
        
        # Инициализация БД (в фоне)
        self.after(100, self.init_db_background)
        
        # Открытие архива если передан
        if archive_to_open and os.path.exists(archive_to_open):
            self.after(200, lambda: self.open_archive_path(archive_to_open))
    
    def setup_icon(self):
        """Установка иконки окна"""
        try:
            # Пробуем загрузить иконку из файла
            if getattr(sys, 'frozen', False):
                # Запущено как exe
                base_path = sys._MEIPASS
                icon_path = os.path.join(base_path, 'icon.ico')
            else:
                # Запущено из скрипта
                icon_path = 'icon.ico'
            
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
            else:
                # Создаем временный файл с иконкой
                import tempfile
                ico_data = create_default_icon()
                with tempfile.NamedTemporaryFile(suffix='.ico', delete=False) as f:
                    f.write(ico_data)
                    temp_icon = f.name
                self.iconbitmap(temp_icon)
                # Удалим после отображения
                self.after(1000, lambda: os.unlink(temp_icon))
        except:
            pass  # Игнорируем ошибки иконки
    
    def setup_ui(self):
        """Быстрая настройка UI"""
        # toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        
        ttk.Button(toolbar, text="Открыть", command=self.open_archive).pack(side="left")
        ttk.Button(toolbar, text="Извлечь", command=self.extract_dialog).pack(side="left")
        ttk.Button(toolbar, text="Пароли", command=self.password_manager).pack(side="left")
        
        # Кнопка "Открыть по умолчанию" - новая!
        ttk.Button(toolbar, text="⭐ Сделать программой по умолчанию", 
                  command=self.make_default_app).pack(side="left", padx=5)
        
        if SV_TTK_AVAILABLE:
            ttk.Button(toolbar, text="Тема", command=self.toggle_theme).pack(side="right")
        else:
            ttk.Button(toolbar, text="Тема (недоступно)", state="disabled").pack(side="right")
        
        # tree
        self.tree = ttk.Treeview(self, columns=("size", "path"))
        self.tree.heading("#0", text="Имя")
        self.tree.heading("size", text="Размер")
        self.tree.heading("path", text="Путь")
        self.tree.pack(expand=True, fill="both")
        
        self.tree.bind("<Double-1>", self.open_file)
        
        # статус
        self.status = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status).pack(fill="x")
        
        # PRO кнопка
        ttk.Button(self, text="💎 Купить PRO версию", command=self.pro_joke).pack(pady=5)
        
        self.dark = False
        if SV_TTK_AVAILABLE:
            sv_ttk.set_theme("light")
    
    def init_db_background(self):
        """Фоновая инициализация БД"""
        global db
        if db is None:
            db = PasswordDB()
        self.log("База данных готова")
    
    def log(self, msg):
        self.status.set(msg)
        self.update_idletasks()
    
    def run_thread(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()
    
    # ---------- АРХИВ ----------
    def open_archive_path(self, path):
        """Открытие архива по пути"""
        if not path or not os.path.exists(path):
            return
        
        self.archive = path
        self.tree.delete(*self.tree.get_children())
        
        # Обновляем заголовок окна
        self.title(f"Modern Archiver - {os.path.basename(path)}")
        
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                for f in zf.infolist():
                    size = f"{f.file_size/1024:.1f} KB" if f.file_size > 0 else "0 B"
                    self.tree.insert("", "end", text=os.path.basename(f.filename),
                                   values=(size, f.filename))
            self.log("Архив открыт")
        except zipfile.BadZipFile:
            messagebox.showerror("Ошибка", "Файл не является ZIP архивом")
            self.archive = None
            self.title("Modern Archiver")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть архив: {e}")
            self.archive = None
            self.title("Modern Archiver")
    
    def open_archive(self):
        path = filedialog.askopenfilename(filetypes=[("ZIP архивы", "*.zip"), ("Все файлы", "*.*")])
        if not path:
            return
        self.open_archive_path(path)
    
    def extract_dialog(self):
        if not self.archive:
            messagebox.showwarning("Предупреждение", "Сначала откройте архив")
            return
        
        dest = filedialog.askdirectory()
        if not dest:
            return
        
        self.run_thread(self.extract_archive, dest)
    
    def extract_archive(self, dest):
        if db is None:
            self.log("Ожидание инициализации БД...")
            time.sleep(0.5)
        
        extract_archive_logic(
            self.archive,
            dest,
            self.log,
            lambda: simpledialog.askstring("Пароль", "Введите пароль", show="*"),
            lambda p: messagebox.askyesno("Сохранить?", "Сохранить пароль?")
        )
        self.log("Извлечение завершено")
    
    # ---------- ОТКРЫТИЕ ФАЙЛА ----------
    def open_file(self, event):
        if not self.archive:
            return
        
        item = self.tree.selection()
        if not item:
            return
        
        path = self.tree.item(item[0])["values"][1]
        self.run_thread(self._open_temp, path)
    
    def _open_temp(self, path):
        try:
            with zipfile.ZipFile(self.archive, 'r') as zf:
                temp_dir = tempfile.mkdtemp()
                extracted = False
                
                try:
                    zf.extract(path, temp_dir)
                    extracted = True
                except:
                    if db:
                        for pwd in db.get_passwords():
                            try:
                                zf.extract(path, temp_dir, pwd=pwd.encode())
                                extracted = True
                                break
                            except:
                                continue
                
                if not extracted:
                    self.log("Не удалось извлечь файл (возможно нужен пароль)")
                    return
                
                file_path = os.path.join(temp_dir, path)
                
                # Открываем файл
                if sys.platform == 'win32':
                    os.startfile(file_path)
                else:
                    subprocess.Popen(['xdg-open', file_path])
                
                # Автоочистка через 60 секунд
                def cleanup():
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        if os.path.exists(temp_dir):
                            os.rmdir(temp_dir)
                    except:
                        pass
                
                self.after(60000, cleanup)
                
        except Exception as e:
            self.log(str(e))
    
    # ---------- ПАРОЛИ ----------
    def password_manager(self):
        if db is None:
            messagebox.showinfo("Информация", "Подождите, база данных инициализируется...")
            return
        
        win = tk.Toplevel(self)
        win.title("Управление паролями")
        win.geometry("400x300")
        
        listbox = tk.Listbox(win)
        listbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        def refresh():
            listbox.delete(0, tk.END)
            for p in db.get_passwords():
                listbox.insert(tk.END, p)
        
        refresh()
        
        def add():
            p = simpledialog.askstring("Добавить пароль", "Введите пароль:", parent=win, show="*")
            if p:
                db.add_password(p)
                refresh()
        
        def delete():
            sel = listbox.curselection()
            if sel:
                if messagebox.askyesno("Удалить", "Удалить выбранный пароль?"):
                    db.delete_password(listbox.get(sel[0]))
                    refresh()
        
        def clear():
            if messagebox.askyesno("Очистить", "Удалить ВСЕ сохраненные пароли?"):
                db.clear_passwords()
                refresh()
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(btn_frame, text="➕ Добавить", command=add).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="❌ Удалить", command=delete).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🗑️ Очистить все", command=clear).pack(side="right", padx=5)
    
    # ---------- НОВАЯ ФУНКЦИЯ: Сделать программой по умолчанию ----------
    def make_default_app(self):
        """Регистрация программы как приложения по умолчанию для .zip файлов"""
        if sys.platform != 'win32':
            messagebox.showinfo("Информация", "Эта функция доступна только в Windows")
            return
        
        try:
            import winreg
            
            # Путь к текущему исполняемому файлу
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            
            # Регистрация в реестре
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Applications\ModernArchiver.exe\shell\open\command") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'{exe_path} "%1"')
            
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.zip\OpenWithProgids") as key:
                winreg.SetValueEx(key, "ModernArchiver", 0, winreg.REG_NONE, None)
            
            messagebox.showinfo("Успех", 
                "Программа зарегистрирована!\n"
                "Теперь можно выбрать её как программу по умолчанию:\n"
                "1. ПКМ на .zip файл -> 'Открыть с помощью' -> 'Выбрать другое приложение'\n"
                "2. Найти Modern Archiver и выбрать 'Всегда использовать'")
            
            # Обновляем shell
            subprocess.run(['cmd', '/c', 'assoc', '.zip=ModernArchiver'], capture_output=True)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось зарегистрировать программу: {e}")
    
    # ---------- ТЕМА ----------
    def toggle_theme(self):
        if not SV_TTK_AVAILABLE:
            return
        self.dark = not self.dark
        sv_ttk.set_theme("dark" if self.dark else "light")
    
    # ---------- PRO ----------
    def pro_joke(self):
        messagebox.showinfo(
            "PRO версия",
            "Чтобы поблагодарить автора, переведите любую сумму \nна номер:\n\n+7 987 254-47-73\n\nСпасибо за поддержку! 💝"
        )


# ---------- СТАРТ ----------
def main():
    """Главная функция с обработкой аргументов командной строки"""
    archive_path = None
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1:
        potential_archive = sys.argv[1]
        if os.path.exists(potential_archive) and potential_archive.lower().endswith('.zip'):
            archive_path = potential_archive
    
    app = App(archive_to_open=archive_path)
    app.mainloop()


if __name__ == "__main__":
    main()
