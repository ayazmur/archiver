# archiver.py
import argparse
import getpass
import os
import sqlite3
import sys
import zipfile

# --- Настройки ---
DB_NAME = "passwords.db"


# --- Функции для работы с базой данных паролей ---

def init_db():
    """Инициализирует базу данных, если она не существует."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS passwords (
            id INTEGER PRIMARY KEY,
            password TEXT NOT NULL UNIQUE
        )
    """)
    conn.commit()
    conn.close()


def add_password_to_db(password):
    """Добавляет новый пароль в базу данных."""
    if not password:
        print("Ошибка: Пустой пароль не может быть добавлен.")
        return
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO passwords (password) VALUES (?)", (password,))
        conn.commit()
        print(f"Пароль '{password}' успешно добавлен в базу.")
    except sqlite3.IntegrityError:
        print(f"Пароль '{password}' уже существует в базе.")
    finally:
        conn.close()


def get_passwords_from_db():
    """Получает все пароли из базы данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM passwords ORDER BY id")
    passwords = [row[0] for row in cursor.fetchall()]
    conn.close()
    return passwords


def list_passwords():
    """Выводит список всех паролей в базе."""
    passwords = get_passwords_from_db()
    if not passwords:
        print("База данных паролей пуста.")
        return
    print("Сохраненные пароли:")
    for pwd in passwords:
        print(f"- {pwd}")


def delete_password_from_db(password):
    """Удаляет пароль из базы данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM passwords WHERE password = ?", (password,))
    if cursor.rowcount > 0:
        print(f"Пароль '{password}' удален из базы.")
    else:
        print(f"Пароль '{password}' не найден в базе.")
    conn.commit()
    conn.close()


# --- Функции для работы с архивами ---

def create_archive(source_path, archive_name, password=None):
    """Создает ZIP-архив из файла или папки."""
    if not os.path.exists(source_path):
        print(f"Ошибка: Исходный путь '{source_path}' не существует.")
        return

    print(f"Создание архива '{archive_name}' из '{source_path}'...")
    with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zf:
        if password:
            zf.setpassword(password.encode('utf-8'))
            print("Архив будет защищен паролем.")

        if os.path.isdir(source_path):
            for root, _, files in os.walk(source_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=source_path)
                    zf.write(file_path, arcname)
        else:
            zf.write(source_path, os.path.basename(source_path))

    print("Архив успешно создан.")
    if password:
        add_password_to_db(password)


def extract_archive(archive_name, dest_path="."):
    """Распаковывает ZIP-архив, используя пароли из базы."""
    if not os.path.exists(archive_name):
        print(f"Ошибка: Архив '{archive_name}' не найден.")
        return

    os.makedirs(dest_path, exist_ok=True)

    try:
        with zipfile.ZipFile(archive_name, 'r') as zf:
            # Сначала пробуем без пароля
            try:
                zf.extractall(path=dest_path)
                print("Архив успешно распакован (пароль не требовался).")
                return
            except RuntimeError as e:
                if "password required" not in str(e).lower():
                    raise  # Другая ошибка, не связанная с паролем

            # Архив запаролен, пробуем пароли из базы
            print("Архив защищен паролем. Пытаюсь подобрать пароль из базы...")
            passwords_to_try = get_passwords_from_db()
            for pwd in passwords_to_try:
                try:
                    zf.extractall(path=dest_path, pwd=pwd.encode('utf-8'))
                    print(f"Успех! Архив распакован с помощью пароля из базы: '{pwd}'")
                    return
                except (RuntimeError, zipfile.BadZipFile):
                    # Неверный пароль, пробуем следующий
                    continue

            # Если пароли из базы не подошли, просим ввести вручную
            print("Пароли из базы не подошли.")
            while True:
                try:
                    manual_pwd = getpass.getpass("Введите пароль вручную (оставьте пустым для отмены): ")
                    if not manual_pwd:
                        print("Распаковка отменена.")
                        return
                    zf.extractall(path=dest_path, pwd=manual_pwd.encode('utf-8'))
                    print("Архив успешно распакован с помощью введенного пароля.")

                    # Спрашиваем, нужно ли сохранить пароль
                    save = input(f"Хотите сохранить этот пароль ('{manual_pwd}') в базу? (y/n): ").lower()
                    if save == 'y':
                        add_password_to_db(manual_pwd)
                    return
                except (RuntimeError, zipfile.BadZipFile):
                    print("Неверный пароль. Попробуйте еще раз.")

    except zipfile.BadZipFile:
        print(f"Ошибка: '{archive_name}' не является корректным ZIP-архивом.")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")


def main():
    """Главная функция для обработки аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Архиватор с базой данных паролей.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Доступные команды")

    # Команда для создания архива
    p_create = subparsers.add_parser("create", help="Создать архив")
    p_create.add_argument("source", help="Исходный файл или папка для архивации")
    p_create.add_argument("archive_name", help="Имя создаваемого архива (например, my_archive.zip)")
    p_create.add_argument("-p", "--password", help="Пароль для архива")

    # Команда для распаковки архива
    p_extract = subparsers.add_parser("extract", help="Распаковать архив")
    p_extract.add_argument("archive_name", help="Имя архива для распаковки")
    p_extract.add_argument("-d", "--dest", default=".", help="Папка назначения для распаковки")

    # Команды для управления паролями
    p_pass = subparsers.add_parser("pass", help="Управление базой паролей")
    pass_subparsers = p_pass.add_subparsers(dest="pass_command", required=True)

    p_pass_add = pass_subparsers.add_parser("add", help="Добавить пароль в базу")
    p_pass_add.add_argument("password", help="Пароль для добавления")

    pass_subparsers.add_parser("list", help="Показать все пароли в базе")

    p_pass_del = pass_subparsers.add_parser("del", help="Удалить пароль из базы")
    p_pass_del.add_argument("password", help="Пароль для удаления")

    args = parser.parse_args()

    init_db()

    if args.command == "create":
        create_archive(args.source, args.archive_name, args.password)
    elif args.command == "extract":
        extract_archive(args.archive_name, args.dest)
    elif args.command == "pass":
        if args.pass_command == "add":
            add_password_to_db(args.password)
        elif args.pass_command == "list":
            list_passwords()
        elif args.pass_command == "del":
            delete_password_from_db(args.password)


if __name__ == "__main__":
    main()