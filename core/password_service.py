import keyring
import json

class PasswordService:
    def __init__(self):
        self.service_name = "ModernArchiver"
        self.username = "user_saved_passwords"

    def get_all(self):
        try:
            data = keyring.get_password(self.service_name, self.username)
            return json.loads(data) if data else []
        except Exception:
            return []

    def add(self, password: str):
        if not password:
            return
        passwords = self.get_all()
        if password not in passwords:
            passwords.append(password)
            self._save(passwords)

    def delete(self, password: str):
        passwords = self.get_all()
        if password in passwords:
            passwords.remove(password)
            self._save(passwords)

    def clear(self):
        self._save([])

    def _save(self, passwords):
        keyring.set_password(self.service_name, self.username, json.dumps(passwords))