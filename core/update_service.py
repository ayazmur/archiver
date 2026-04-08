import requests


class UpdateService:
    def __init__(self, repo):
        self.repo = repo  # "username/repo"

    def check_update(self):
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        r = requests.get(url)

        if r.status_code != 200:
            return None

        data = r.json()
        return {
            "version": data["tag_name"],
            "download": data["assets"][0]["browser_download_url"]
        }