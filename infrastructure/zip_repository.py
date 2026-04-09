import zipfile
import py7zr
import rarfile
import tarfile
import os

class ArchiveRepository:
    def __init__(self):
        self.handlers = {
            '.zip': ZipHandler(),
            '.7z': SevenZipHandler(),
            '.rar': RarHandler(),
            '.tar': TarHandler(),
            '.tar.gz': TarHandler(),
            '.tgz': TarHandler(),
        }

    def get_handler(self, path):
        ext = self._get_extension(path)
        return self.handlers.get(ext)

    def _get_extension(self, path):
        path = path.lower()
        for ext in ['.tar.gz', '.tar.bz2', '.tgz']:
            if path.endswith(ext): return ext
        return os.path.splitext(path)[1]

class ZipHandler:
    def check_password(self, path, password=None):
        try:
            with zipfile.ZipFile(path) as zf:
                if password: zf.setpassword(password.encode())
                return zf.testzip() is None
        except: return False

    def extract_all(self, path, dest, password=None):
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(dest, pwd=password.encode() if password else None)
            return True
        except: return False

class SevenZipHandler:
    def check_password(self, path, password=None):
        try:
            with py7zr.SevenZipFile(path, mode='r', password=password) as szf:
                return szf.needs_password() is False or password is not None
        except: return False

    def extract_all(self, path, dest, password=None):
        try:
            with py7zr.SevenZipFile(path, mode='r', password=password) as szf:
                szf.extractall(dest)
            return True
        except: return False

class RarHandler:
    def check_password(self, path, password=None):
        try:
            with rarfile.RarFile(path) as rf:
                rf.needs_password()
                if password: rf.setpassword(password)
                rf.testrar()
                return True
        except: return False

    def extract_all(self, path, dest, password=None):
        try:
            with rarfile.RarFile(path, pwd=password) as rf:
                rf.extractall(dest)
            return True
        except: return False

class TarHandler:
    def check_password(self, path, password=None): return True # Tar не поддерживает пароли
    def extract_all(self, path, dest, password=None):
        try:
            with tarfile.open(path, 'r:*') as tf:
                tf.extractall(dest)
            return True
        except: return False