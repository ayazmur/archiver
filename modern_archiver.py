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

import sv_ttk

DB_NAME = "passwords.db"


# ---------- БАЗА ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS passwords (id INTEGER PRIMARY KEY, password TEXT UNIQUE)")
    conn.commit()
    conn.close()


def add_password_to_db(password):
    if not password:
        return
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO passwords (password) VALUES (?)", (password,))
        conn.commit()
    except:
        pass
    finally:
        conn.close()


def get_passwords_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM passwords")
    data = [row[0] for row in cursor.fetchall()]
    conn.close()
    return data


def delete_password(pwd):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM passwords WHERE password=?", (pwd,))
    conn.commit()
    conn.close()


def clear_passwords():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM passwords")
    conn.commit()
    conn.close()


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
            for pwd in get_passwords_from_db():
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
                        add_password_to_db(pwd)
                    return True
                except:
                    if not messagebox.askretrycancel("Ошибка", "Неверный пароль"):
                        return False

    except Exception as e:
        log(str(e))
        return False


# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modern Archiver")
        self.geometry("800x600")

        self.archive = None

        # toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Открыть", command=self.open_archive).pack(side="left")
        ttk.Button(toolbar, text="Извлечь", command=self.extract_dialog).pack(side="left")
        ttk.Button(toolbar, text="Пароли", command=self.password_manager).pack(side="left")
        ttk.Button(toolbar, text="Тема", command=self.toggle_theme).pack(side="right")

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

        # ПРО кнопка 😄
        ttk.Button(self, text="💎 Купить PRO версию", command=self.pro_joke).pack(pady=5)

        self.dark = False
        init_db()

    # ---------- UI ----------
    def log(self, msg):
        self.status.set(msg)
        self.update()

    def run_thread(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    # ---------- АРХИВ ----------
    def open_archive(self):
        path = filedialog.askopenfilename(filetypes=[("ZIP", "*.zip")])
        if not path:
            return

        self.archive = path
        self.tree.delete(*self.tree.get_children())

        with zipfile.ZipFile(path, 'r') as zf:
            for f in zf.infolist():
                size = f"{f.file_size/1024:.1f} KB"
                self.tree.insert("", "end", text=os.path.basename(f.filename),
                                 values=(size, f.filename))

        self.log("Архив открыт")

    def extract_dialog(self):
        if not self.archive:
            return

        dest = filedialog.askdirectory()
        if not dest:
            return

        self.run_thread(self.extract_archive, dest)

    def extract_archive(self, dest):
        extract_archive_logic(
            self.archive,
            dest,
            self.log,
            lambda: simpledialog.askstring("Пароль", "Введите пароль", show="*"),
            lambda p: messagebox.askyesno("Сохранить?", "Сохранить пароль?")
        )

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
                try:
                    zf.extract(path, temp_dir)
                except:
                    for pwd in get_passwords_from_db():
                        try:
                            zf.extract(path, temp_dir, pwd=pwd.encode())
                            break
                        except:
                            continue

                file_path = os.path.join(temp_dir, path)

                subprocess.Popen(file_path, shell=True)

                time.sleep(60)

                try:
                    os.remove(file_path)
                    os.rmdir(temp_dir)
                except:
                    pass

        except Exception as e:
            self.log(str(e))

    # ---------- ПАРОЛИ ----------
    def password_manager(self):
        win = tk.Toplevel(self)
        win.title("Пароли")

        listbox = tk.Listbox(win)
        listbox.pack(fill="both", expand=True)

        def refresh():
            listbox.delete(0, tk.END)
            for p in get_passwords_from_db():
                listbox.insert(tk.END, p)

        refresh()

        def add():
            p = simpledialog.askstring("Пароль", "Введите", parent=win)
            if p:
                add_password_to_db(p)
                refresh()

        def delete():
            sel = listbox.curselection()
            if sel:
                delete_password(listbox.get(sel[0]))
                refresh()

        def clear():
            if messagebox.askyesno("Очистить", "Все пароли?"):
                clear_passwords()
                refresh()

        ttk.Button(win, text="Добавить", command=add).pack(side="left")
        ttk.Button(win, text="Удалить", command=delete).pack(side="left")
        ttk.Button(win, text="Очистить", command=clear).pack(side="right")

    # ---------- ТЕМА ----------
    def toggle_theme(self):
        self.dark = not self.dark
        sv_ttk.set_theme("dark" if self.dark else "light")

    # ---------- ШУТКА 😄 ----------
    def pro_joke(self):
        messagebox.showinfo(
            "PRO версия",
            "Чтобы поблагодарить аффтора, переведите любую сумму \nна номер:\n\n89872544773\n\nСпасибо"
        )


# ---------- СТАРТ ----------
if __name__ == "__main__":
    app = App()
    sv_ttk.set_theme("light")
    app.mainloop()