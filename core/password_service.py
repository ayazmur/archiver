import time


class PasswordService:
    def __init__(self, repository):
        self.repo = repository
        self._cache = None
        self._cache_time = 0
        self._ttl = 5

    def _is_cache_valid(self):
        return self._cache and (time.time() - self._cache_time < self._ttl)

    def get_all(self):
        if self._is_cache_valid():
            return self._cache.copy()

        data = self.repo.load()
        passwords = data.get("passwords", [])

        self._cache = passwords
        self._cache_time = time.time()

        return passwords.copy()

    def add(self, password: str):
        if not password:
            return

        passwords = self.get_all()
        if password not in passwords:
            passwords.append(password)
            self.repo.save({"passwords": passwords})

    def delete(self, password: str):
        passwords = self.get_all()
        if password in passwords:
            passwords.remove(password)
            self.repo.save({"passwords": passwords})

    def clear(self):
        self.repo.save({"passwords": []})