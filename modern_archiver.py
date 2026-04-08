import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import sys
import threading
import zipfile
import json
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


# ---------- УПРАВЛЕНИЕ ПАРОЛЯМИ В APPDATA ----------
class PasswordManager:
    """Класс для работы с паролями через JSON в AppData"""
    _instance = None
    _cache = None
    _cache_time = 0
    _cache_duration = 5  # кэш на 5 секунд

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_storage()
        return cls._instance

    def _get_app_data_dir(self):
        """Получение пути к папке AppData/Roaming/ModernArchiver"""
        if sys.platform == 'win32':
            app_data = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:
            # Для Linux/Mac используем ~/.config
            app_data = os.path.expanduser('~/.config')

        app_dir = os.path.join(app_data, 'ModernArchiver')
        os.makedirs(app_dir, exist_ok=True)
        return app_dir

    def _get_passwords_file(self):
        """Получение пути к файлу с паролями"""
        return os.path.join(self._get_app_data_dir(), 'passwords.json')

    def _get_config_file(self):
        """Получение пути к файлу конфигурации"""
        return os.path.join(self._get_app_data_dir(), 'config.json')

    def _init_storage(self):
        """Инициализация хранилища (создание файлов если их нет)"""
        passwords_file = self._get_passwords_file()
        if not os.path.exists(passwords_file):
            self._save_passwords([])

        config_file = self._get_config_file()
        if not os.path.exists(config_file):
            default_config = {
                "theme": "light",
                "last_archives": [],
                "max_recent": 10
            }
            self._save_json(config_file, default_config)

    def _save_json(self, file_path, data):
        """Сохранение данных в JSON файл"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_json(self, file_path, default=None):
        """Загрузка данных из JSON файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default if default is not None else []

    def _save_passwords(self, passwords):
        """Сохранение паролей в файл"""
        self._save_json(self._get_passwords_file(), {"passwords": passwords})
        self._cache = passwords
        self._cache_time = time.time()

    def _is_cache_valid(self):
        """Проверка валидности кэша"""
        return self._cache is not None and (time.time() - self._cache_time) < self._cache_duration

    def add_password(self, password):
        """Добавление пароля"""
        if not password:
            return

        passwords = self.get_passwords()
        if password not in passwords:
            passwords.append(password)
            self._save_passwords(passwords)

    def get_passwords(self):
        """Получение всех паролей с кэшированием"""
        if self._is_cache_valid():
            return self._cache.copy()

        data = self._load_json(self._get_passwords_file(), {"passwords": []})
        passwords = data.get("passwords", [])

        self._cache = passwords
        self._cache_time = time.time()
        return passwords.copy()

    def delete_password(self, password):
        """Удаление пароля"""
        passwords = self.get_passwords()
        if password in passwords:
            passwords.remove(password)
            self._save_passwords(passwords)

    def clear_passwords(self):
        """Очистка всех паролей"""
        self._save_passwords([])

    def get_config(self):
        """Получение конфигурации"""
        return self._load_json(self._get_config_file(), {})

    def save_config(self, key, value):
        """Сохранение настройки"""
        config = self.get_config()
        config[key] = value
        self._save_json(self._get_config_file(), config)

    def add_recent_archive(self, archive_path):
        """Добавление архива в список недавних"""
        config = self.get_config()
        recent = config.get("last_archives", [])
        max_recent = config.get("max_recent", 10)

        # Удаляем если уже есть
        if archive_path in recent:
            recent.remove(archive_path)

        # Добавляем в начало
        recent.insert(0, archive_path)

        # Ограничиваем количество
        if len(recent) > max_recent:
            recent = recent[:max_recent]

        config["last_archives"] = recent
        self._save_json(self._get_config_file(), config)


# Глобальный экземпляр менеджера паролей
pwd_manager = None


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

            # пробуем сохраненные пароли
            for pwd in pwd_manager.get_passwords():
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
                        pwd_manager.add_password(pwd)
                    return True
                except:
                    if not messagebox.askretrycancel("Ошибка", "Неверный пароль"):
                        return False

    except Exception as e:
        log(str(e))
        return False


# ---------- СОЗДАНИЕ ИКОНКИ ----------
def create_icon_from_svg():
    """Конвертирует SVG в ICO используя PIL/CairoSVG"""
    try:
        from PIL import Image
        import cairosvg

        svg_path = 'icon.svg'
        ico_path = 'icon.ico'

        if not os.path.exists(svg_path):
            return False

        # Конвертируем SVG в PNG разных размеров
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        images = []

        for size in sizes:
            png_data = cairosvg.svg2png(url=svg_path, output_width=size[0], output_height=size[1])
            img = Image.open(io.BytesIO(png_data))
            images.append(img)

        # Сохраняем как ICO
        images[0].save(ico_path, format='ICO', append_images=images[1:])
        return True
    except Exception as e:
        print(f"Не удалось создать иконку: {e}")
        return False


# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self, archive_to_open=None):
        super().__init__()
        self.title("Modern Archiver")
        self.geometry("800x600")

        # Установка иконки
        self.setup_icon()

        self.archive = None

        # Создание GUI
        self.setup_ui()

        # Инициализация менеджера паролей (в фоне)
        self.after(100, self.init_manager_background)

        # Открытие архива если передан
        if archive_to_open and os.path.exists(archive_to_open):
            self.after(200, lambda: self.open_archive_path(archive_to_open))

    def setup_icon(self):
        """Установка иконки окна"""
        try:
            # Пробуем создать иконку из SVG
            if os.path.exists('icon.svg'):
                create_icon_from_svg()

            # Загружаем иконку
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
                icon_path = os.path.join(base_path, 'icon.ico')
            else:
                icon_path = 'icon.ico'

            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except:
            pass  # Игнорируем ошибки иконки

    def setup_ui(self):
        """Настройка UI"""
        # Главный контейнер
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True)

        # Меню
        self.setup_menu()

        # toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="📂 Открыть", command=self.open_archive).pack(side="left", padx=2)
        ttk.Button(toolbar, text="📦 Извлечь", command=self.extract_dialog).pack(side="left", padx=2)
        ttk.Button(toolbar, text="🔑 Пароли", command=self.password_manager).pack(side="left", padx=2)

        # Кнопка недавних архивов
        self.recent_btn = ttk.Menubutton(toolbar, text="📋 Недавние")
        self.recent_btn.pack(side="left", padx=2)
        self.recent_menu = tk.Menu(self.recent_btn, tearoff=0)
        self.recent_btn["menu"] = self.recent_menu
        self.update_recent_menu()

        ttk.Button(toolbar, text="⭐ Сделать программой по умолчанию",
                   command=self.make_default_app).pack(side="left", padx=5)

        if SV_TTK_AVAILABLE:
            ttk.Button(toolbar, text="🎨 Тема", command=self.toggle_theme).pack(side="right", padx=2)

        # tree
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True)

        # Добавляем scrollbar
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        self.tree = ttk.Treeview(tree_frame, columns=("size", "path"),
                                 yscrollcommand=tree_scroll.set)
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("#0", text="Имя")
        self.tree.heading("size", text="Размер")
        self.tree.heading("path", text="Путь")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Double-1>", self.open_file)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Контекстное меню
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="📂 Открыть", command=self.open_selected_file)
        self.context_menu.add_command(label="📋 Копировать путь", command=self.copy_file_path)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📦 Извлечь выбранное", command=self.extract_selected)

        # статус
        self.status = tk.StringVar(value="✅ Готово")
        status_bar = ttk.Label(main_frame, textvariable=self.status, relief="sunken")
        status_bar.pack(fill="x")

        # PRO кнопка
        pro_btn = ttk.Button(main_frame, text="❤️ Поблагодарить автора", command=self.pro_joke)
        pro_btn.pack(pady=5)

        self.dark = False
        if SV_TTK_AVAILABLE:
            # Загружаем сохраненную тему
            if pwd_manager:
                config = pwd_manager.get_config()
                theme = config.get("theme", "light")
                sv_ttk.set_theme(theme)
                self.dark = (theme == "dark")
            else:
                sv_ttk.set_theme("light")

    def setup_menu(self):
        """Создание главного меню"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="📂 Открыть архив", command=self.open_archive)
        file_menu.add_command(label="📋 Недавние архивы", command=self.show_recent_archives)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Выход", command=self.quit)

        # Инструменты
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Инструменты", menu=tools_menu)
        tools_menu.add_command(label="🔑 Управление паролями", command=self.password_manager)
        tools_menu.add_command(label="⚙️ Настройки", command=self.show_settings)

        # Помощь
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Помощь", menu=help_menu)
        help_menu.add_command(label="📖 О программе", command=self.show_about)
        help_menu.add_command(label="❤️ Поблагодарить", command=self.pro_joke)

    def init_manager_background(self):
        """Фоновая инициализация менеджера паролей"""
        global pwd_manager
        if pwd_manager is None:
            pwd_manager = PasswordManager()
        self.log("Хранилище паролей готово")
        self.update_recent_menu()

    def log(self, msg):
        self.status.set(f"📌 {msg}")
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
                    size = f"{f.file_size / 1024:.1f} KB" if f.file_size > 0 else "0 B"
                    # Определяем иконку для файла
                    icon = "📄"
                    if f.is_dir():
                        icon = "📁"
                    elif f.filename.endswith(('.jpg', '.png', '.gif')):
                        icon = "🖼️"
                    elif f.filename.endswith(('.mp3', '.wav')):
                        icon = "🎵"
                    elif f.filename.endswith(('.mp4', '.avi')):
                        icon = "🎬"

                    self.tree.insert("", "end", text=f"{icon} {os.path.basename(f.filename)}",
                                     values=(size, f.filename))

            self.log("Архив открыт")

            # Добавляем в недавние
            if pwd_manager:
                pwd_manager.add_recent_archive(path)
                self.update_recent_menu()

        except zipfile.BadZipFile:
            messagebox.showerror("Ошибка", "Файл не является ZIP архивом")
            self.archive = None
            self.title("Modern Archiver")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть архив: {e}")
            self.archive = None
            self.title("Modern Archiver")

    def open_archive(self):
        path = filedialog.askopenfilename(
            filetypes=[("ZIP архивы", "*.zip"), ("Все файлы", "*.*")]
        )
        if not path:
            return
        self.open_archive_path(path)

    def update_recent_menu(self):
        """Обновление меню недавних архивов"""
        self.recent_menu.delete(0, tk.END)

        if not pwd_manager:
            return

        config = pwd_manager.get_config()
        recent = config.get("last_archives", [])

        if recent:
            for path in recent[:10]:
                if os.path.exists(path):
                    display_name = os.path.basename(path)
                    self.recent_menu.add_command(
                        label=display_name,
                        command=lambda p=path: self.open_archive_path(p)
                    )
            self.recent_menu.add_separator()
            self.recent_menu.add_command(
                label="Очистить список",
                command=self.clear_recent_archives
            )
        else:
            self.recent_menu.add_command(label="Нет недавних архивов", state="disabled")

    def clear_recent_archives(self):
        """Очистка списка недавних архивов"""
        if pwd_manager:
            pwd_manager.save_config("last_archives", [])
            self.update_recent_menu()

    def show_recent_archives(self):
        """Показать окно с недавними архивами"""
        if not pwd_manager:
            return

        config = pwd_manager.get_config()
        recent = config.get("last_archives", [])

        if not recent:
            messagebox.showinfo("Информация", "Список недавних архивов пуст")
            return

        win = tk.Toplevel(self)
        win.title("Недавние архивы")
        win.geometry("500x300")

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        listbox = tk.Listbox(frame)
        listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=listbox.yview)

        for path in recent:
            if os.path.exists(path):
                listbox.insert(tk.END, path)

        def open_selected():
            selection = listbox.curselection()
            if selection:
                path = listbox.get(selection[0])
                win.destroy()
                self.open_archive_path(path)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(btn_frame, text="📂 Открыть", command=open_selected).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🗑️ Очистить",
                   command=lambda: [self.clear_recent_archives(), win.destroy()]).pack(side="right", padx=5)

    def extract_dialog(self):
        if not self.archive:
            messagebox.showwarning("Предупреждение", "Сначала откройте архив")
            return

        dest = filedialog.askdirectory()
        if not dest:
            return

        self.run_thread(self.extract_archive, dest)

    def extract_archive(self, dest):
        if pwd_manager is None:
            self.log("Ожидание инициализации хранилища...")
            time.sleep(0.5)

        extract_archive_logic(
            self.archive,
            dest,
            self.log,
            lambda: simpledialog.askstring("Пароль", "Введите пароль", show="*"),
            lambda p: messagebox.askyesno("Сохранить?", "Сохранить пароль?")
        )
        self.log("✅ Извлечение завершено")

    # ---------- ОТКРЫТИЕ ФАЙЛА ----------
    def open_file(self, event):
        self.open_selected_file()

    def open_selected_file(self):
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
                    if pwd_manager:
                        for pwd in pwd_manager.get_passwords():
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

    def show_context_menu(self, event):
        """Показ контекстного меню"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def copy_file_path(self):
        """Копирование пути файла в буфер обмена"""
        selection = self.tree.selection()
        if selection:
            path = self.tree.item(selection[0])["values"][1]
            self.clipboard_clear()
            self.clipboard_append(path)
            self.log(f"Путь скопирован: {path}")

    def extract_selected(self):
        """Извлечение выбранных файлов"""
        if not self.archive:
            return

        selection = self.tree.selection()
        if not selection:
            return

        dest = filedialog.askdirectory()
        if not dest:
            return

        self.run_thread(self._extract_selected_files, selection, dest)

    def _extract_selected_files(self, selection, dest):
        """Извлечение выбранных файлов в отдельном потоке"""
        try:
            with zipfile.ZipFile(self.archive, 'r') as zf:
                for item in selection:
                    path = self.tree.item(item)["values"][1]

                    extracted = False
                    try:
                        zf.extract(path, dest)
                        extracted = True
                    except:
                        if pwd_manager:
                            for pwd in pwd_manager.get_passwords():
                                try:
                                    zf.extract(path, dest, pwd=pwd.encode())
                                    extracted = True
                                    break
                                except:
                                    continue

                    if not extracted:
                        pwd = simpledialog.askstring("Пароль", f"Введите пароль для {path}", show="*")
                        if pwd:
                            try:
                                zf.extract(path, dest, pwd=pwd.encode())
                                if messagebox.askyesno("Сохранить?", "Сохранить пароль?"):
                                    pwd_manager.add_password(pwd)
                            except:
                                self.log(f"Не удалось извлечь: {path}")

            self.log("✅ Извлечение выбранных файлов завершено")
        except Exception as e:
            self.log(f"Ошибка: {e}")

    # ---------- ПАРОЛИ ----------
    def password_manager(self):
        if pwd_manager is None:
            messagebox.showinfo("Информация", "Подождите, хранилище инициализируется...")
            return

        win = tk.Toplevel(self)
        win.title("Управление паролями")
        win.geometry("400x300")

        # Показываем путь к файлу
        path_frame = ttk.Frame(win)
        path_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(path_frame, text="📁 Файл паролей:").pack(side="left")
        path_label = ttk.Label(path_frame, text=pwd_manager._get_passwords_file(),
                               foreground="gray")
        path_label.pack(side="left", padx=5)

        listbox = tk.Listbox(win)
        listbox.pack(fill="both", expand=True, padx=10, pady=5)

        def refresh():
            listbox.delete(0, tk.END)
            for p in pwd_manager.get_passwords():
                listbox.insert(tk.END, p)

        refresh()

        def add():
            p = simpledialog.askstring("Добавить пароль", "Введите пароль:", parent=win, show="*")
            if p:
                pwd_manager.add_password(p)
                refresh()

        def delete():
            sel = listbox.curselection()
            if sel:
                if messagebox.askyesno("Удалить", "Удалить выбранный пароль?"):
                    pwd_manager.delete_password(listbox.get(sel[0]))
                    refresh()

        def clear():
            if messagebox.askyesno("Очистить", "Удалить ВСЕ сохраненные пароли?"):
                pwd_manager.clear_passwords()
                refresh()

        def export():
            """Экспорт паролей в текстовый файл"""
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Текстовые файлы", "*.txt")]
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for p in pwd_manager.get_passwords():
                        f.write(p + '\n')
                messagebox.showinfo("Экспорт", f"Пароли экспортированы в {file_path}")

        def import_passwords():
            """Импорт паролей из текстового файла"""
            file_path = filedialog.askopenfilename(
                filetypes=[("Текстовые файлы", "*.txt")]
            )
            if file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        p = line.strip()
                        if p:
                            pwd_manager.add_password(p)
                refresh()
                messagebox.showinfo("Импорт", "Пароли импортированы")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(btn_frame, text="➕ Добавить", command=add).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="❌ Удалить", command=delete).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="📤 Экспорт", command=export).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="📥 Импорт", command=import_passwords).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="🗑️ Очистить все", command=clear).pack(side="right", padx=2)

    # ---------- НАСТРОЙКИ ----------
    def show_settings(self):
        """Показать окно настроек"""
        if not pwd_manager:
            messagebox.showinfo("Информация", "Подождите, хранилище инициализируется...")
            return

        win = tk.Toplevel(self)
        win.title("Настройки")
        win.geometry("400x250")

        config = pwd_manager.get_config()

        # Путь к папке программы
        frame1 = ttk.LabelFrame(win, text="Расположение данных", padding=10)
        frame1.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame1, text=f"📁 Папка: {pwd_manager._get_app_data_dir()}").pack(anchor="w")
        ttk.Label(frame1, text=f"📄 Пароли: {pwd_manager._get_passwords_file()}").pack(anchor="w")

        # Тема
        if SV_TTK_AVAILABLE:
            frame2 = ttk.LabelFrame(win, text="Оформление", padding=10)
            frame2.pack(fill="x", padx=10, pady=5)

            theme_var = tk.StringVar(value=config.get("theme", "light"))
            ttk.Radiobutton(frame2, text="Светлая тема", variable=theme_var,
                            value="light").pack(anchor="w")
            ttk.Radiobutton(frame2, text="Темная тема", variable=theme_var,
                            value="dark").pack(anchor="w")

        # Недавние архивы
        frame3 = ttk.LabelFrame(win, text="Недавние архивы", padding=10)
        frame3.pack(fill="x", padx=10, pady=5)

        max_recent_var = tk.StringVar(value=str(config.get("max_recent", 10)))
        ttk.Label(frame3, text="Максимальное количество:").pack(anchor="w")
        ttk.Spinbox(frame3, from_=5, to=50, textvariable=max_recent_var, width=10).pack(anchor="w")

        def save_settings():
            if SV_TTK_AVAILABLE:
                new_theme = theme_var.get()
                pwd_manager.save_config("theme", new_theme)
                if new_theme != ("dark" if self.dark else "light"):
                    self.toggle_theme()

            try:
                max_recent = int(max_recent_var.get())
                if 5 <= max_recent <= 50:
                    pwd_manager.save_config("max_recent", max_recent)
            except:
                pass

            win.destroy()
            messagebox.showinfo("Настройки", "Настройки сохранены")

        ttk.Button(win, text="Сохранить", command=save_settings).pack(pady=10)

    def show_about(self):
        """Показать окно о программе"""
        about_text = """Modern Archiver v2.0

Усовершенствованный архиватор с поддержкой паролей.

Особенности:
• Открытие защищенных паролем ZIP архивов
• Сохранение паролей в зашифрованном виде
• Просмотр содержимого без извлечения
• Извлечение отдельных файлов
• Тёмная и светлая темы

Автор: Ваше имя
Лицензия: MIT
        """
        messagebox.showinfo("О программе", about_text)

    # ---------- СДЕЛАТЬ ПРОГРАММОЙ ПО УМОЛЧАНИЮ ----------
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
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\Applications\ModernArchiver.exe\shell\open\command") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'{exe_path} "%1"')

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.zip\OpenWithProgids") as key:
                winreg.SetValueEx(key, "ModernArchiver", 0, winreg.REG_NONE, None)

            messagebox.showinfo("Успех",
                                "✅ Программа зарегистрирована!\n\n"
                                "Теперь можно выбрать её как программу по умолчанию:\n"
                                "1️⃣ ПКМ на .zip файл\n"
                                "2️⃣ 'Открыть с помощью' → 'Выбрать другое приложение'\n"
                                "3️⃣ Найти Modern Archiver и выбрать 'Всегда использовать'")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось зарегистрировать программу: {e}")

    # ---------- ТЕМА ----------
    def toggle_theme(self):
        if not SV_TTK_AVAILABLE:
            return
        self.dark = not self.dark
        sv_ttk.set_theme("dark" if self.dark else "light")
        if pwd_manager:
            pwd_manager.save_config("theme", "dark" if self.dark else "light")

    # ---------- PRO ----------
    def pro_joke(self):
        messagebox.showinfo(
            "Донат",
            "Чтобы поблагодарить автора, переведите любую сумму\n\n"
            "📱 +7 987 254-47-73 (Сбербанк)\n"
            "Спасибо за поддержку! ❤️"
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