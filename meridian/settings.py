"""Local connection configuration. Installed app secrets live in macOS Keychain."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

SECRET_KEYS = {
    "CANVAS_TOKEN",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "GMAIL_ACCESS_TOKEN",
    "GOOGLE_ACCOUNTS",
}
CONFIG_KEYS = {"CANVAS_BASE_URL", "GOOGLE_CLIENT_ID", "GOOGLE_EMAIL"}
ALL_KEYS = SECRET_KEYS | CONFIG_KEYS


class Settings:
    def __init__(self, directory=None):
        self.directory = Path(
            directory or os.getenv("MERIDIAN_SETTINGS_DIR", "data/settings")
        )
        self.helper = os.getenv("MERIDIAN_KEYCHAIN_HELPER")

    def _read(self, name):
        try:
            return json.loads((self.directory / name).read_text())
        except FileNotFoundError:
            return {}

    def _write(self, name, data):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, path = tempfile.mkstemp(dir=self.directory, prefix=".settings-")
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(data, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(path, self.directory / name)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def _keychain(self, action, key, value=""):
        result = subprocess.run(
            [self.helper, "--keychain"],
            input=json.dumps({"action": action, "key": key, "value": value}),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                "macOS Keychain access failed. Unlock your login keychain and try again."
            )
        data = json.loads(result.stdout)
        return data.get("value", "")

    def stored(self, key):
        if key not in ALL_KEYS:
            raise ValueError("Unknown setting")
        if key in SECRET_KEYS and self.helper:
            return self._keychain("get", key)
        return self._read(
            "secrets.json" if key in SECRET_KEYS else "connections.json"
        ).get(key, "")

    def get(self, key):
        return self.stored(key) or os.getenv(key, "")

    def set(self, key, value):
        if key not in ALL_KEYS:
            raise ValueError("Unknown setting")
        if key in SECRET_KEYS and self.helper:
            self._keychain("set" if value else "delete", key, value)
        else:
            name = "secrets.json" if key in SECRET_KEYS else "connections.json"
            data = self._read(name)
            if value:
                data[key] = value
            else:
                data.pop(key, None)
            self._write(name, data)
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    def load(self):
        for key in ALL_KEYS:
            value = self.stored(key)
            if value:
                os.environ[key] = value

    def status(self):
        accounts = json.loads(self.get("GOOGLE_ACCOUNTS") or "{}")
        return {
            "accounts": sorted(accounts),
            "canvas": bool(self.get("CANVAS_TOKEN")),
            "gmail": bool(
                accounts
                or self.get("GOOGLE_REFRESH_TOKEN")
                or self.get("GMAIL_ACCESS_TOKEN")
            ),
            "google_client": bool(self.get("GOOGLE_CLIENT_ID")),
            "google_email": ", ".join(sorted(accounts)) or self.get("GOOGLE_EMAIL"),
            "canvas_url": self.get("CANVAS_BASE_URL") or "https://canvas.cornell.edu",
            "storage": (
                "macOS Keychain"
                if self.helper
                else "local files with owner-only permissions"
            ),
        }
