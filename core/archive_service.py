class ArchiveService:
    def __init__(self, archive_repo, password_service):
        self.archive_repo = archive_repo
        self.password_service = password_service

    def get_supported_formats(self):
        return list(self.archive_repo.handlers.keys())

    def extract_all(self, archive_path, dest, ask_password_func):
        handler = self.archive_repo.get_handler(archive_path)
        if not handler: return False

        # 1. Пробуем без пароля
        if handler.check_password(archive_path):
            return handler.extract_all(archive_path, dest)

        # 2. Пробуем сохраненные (быстрая проверка)
        for pwd in self.password_service.get_all():
            if handler.check_password(archive_path, pwd):
                return handler.extract_all(archive_path, dest, pwd)

        # 3. Спрашиваем пользователя
        while True:
            pwd = ask_password_func()
            if not pwd: return False
            if handler.check_password(archive_path, pwd):
                self.password_service.add(pwd) # Запоминаем новый пароль!
                return handler.extract_all(archive_path, dest, pwd)