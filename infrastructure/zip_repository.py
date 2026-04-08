import zipfile


class ZipRepository:
    def list_files(self, archive_path):
        result = []

        with zipfile.ZipFile(archive_path, 'r') as zf:
            for f in zf.infolist():
                result.append({
                    "name": f.filename,
                    "size": f.file_size,
                    "is_dir": f.is_dir()
                })

        return result

    def extract_all(self, archive_path, dest, password=None):
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                if password:
                    zf.extractall(dest, pwd=password.encode())
                else:
                    zf.extractall(dest)
            return True
        except:
            return False