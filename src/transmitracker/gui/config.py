"""Project-local preferences and explicitly unencrypted, masked-in-UI secrets."""

import json
import re
from pathlib import Path

SECRET_KEYS = ("CROMA_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


class LocalConfig:
    def __init__(self, root: Path, directory="data/gui"):
        self.root = root.resolve()
        self.directory = self.local(directory)
        self.path = self.local(self.directory / "settings.json")
        self.env_path = self.local(".env")

    def local(self, value):
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("La ruta debe permanecer dentro de TransMiTracker.")
        return path

    def read(self):
        defaults = {
            "theme": "Oscuro",
            "catalog_path": "data/catalog/official_20261112.sqlite3",
            "collection_interval": 120,
            "notifications_enabled": False,
            "example_departures": {},
        }
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Configuración local inválida; no se sobrescribió.")
            defaults.update({k: data[k] for k in defaults if k in data})
        self.local(defaults["catalog_path"])
        if defaults["theme"] not in ("Oscuro", "Claro"):
            raise ValueError("Tema local inválido.")
        if type(defaults["notifications_enabled"]) is not bool or not isinstance(
            defaults["example_departures"], dict
        ):
            raise ValueError("Preferencias locales inválidas.")
        return defaults

    def write(self, preferences):
        if set(preferences) - set(self.read()):
            raise ValueError("No se admiten secretos ni campos desconocidos en preferencias.")
        self.local(preferences["catalog_path"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.local(self.directory / "settings.json.tmp")
        temporary.write_text(
            json.dumps(preferences, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(self.path)

    def read_secrets(self):
        values = dict.fromkeys(SECRET_KEYS, "")
        if not self.env_path.exists():
            return values
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            match = re.match(
                r"^\s*(CROMA_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)\s*=(.*)$", line
            )
            if match:
                value = match[2].strip()
                if value.startswith('"'):
                    value = json.loads(value)
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                if not isinstance(value, str):
                    raise ValueError("Formato de .env inválido; revise el archivo local.")
                values[match[1]] = value
        return values

    def write_secrets(self, values):
        if set(values) != set(SECRET_KEYS) or any(not isinstance(v, str) for v in values.values()):
            raise ValueError("Campos de credenciales inválidos.")
        lines = (
            self.env_path.read_text(encoding="utf-8").splitlines() if self.env_path.exists() else []
        )
        lines = [
            line
            for line in lines
            if not re.match(r"^\s*(CROMA_API_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)\s*=", line)
        ]
        lines += [f"{key}={json.dumps(values[key], ensure_ascii=False)}" for key in SECRET_KEYS]
        temporary = self.local(".env.tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(self.env_path)
