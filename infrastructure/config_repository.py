import json
import os


class ConfigRepository:
    def __init__(self, filename):
        self.path = self._get_path(filename)
        self._ensure_exists()

    def _get_path(self, filename):
        base = os.path.expanduser("~/.config/ModernArchiver")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, filename)

    def _ensure_exists(self):
        if not os.path.exists(self.path):
            self.save({})

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)