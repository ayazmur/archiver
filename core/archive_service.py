class ArchiveService:
    def __init__(self, zip_repo, password_service):
        self.zip_repo = zip_repo
        self.password_service = password_service

    def list_files(self, archive_path):
        return self.zip_repo.list_files(archive_path)

    def extract_all(self, archive_path, dest, ask_password):
        try:
            self.zip_repo.extract_all(archive_path, dest)
            return True
        except RuntimeError:
            pass

        # пробуем сохраненные пароли
        for pwd in self.password_service.get_all():
            if self.zip_repo.extract_all(archive_path, dest, pwd):
                return True

        # спрашиваем у пользователя
        while True:
            pwd = ask_password()
            if not pwd:
                return False

            if self.zip_repo.extract_all(archive_path, dest, pwd):
                self.password_service.add(pwd)
                return True