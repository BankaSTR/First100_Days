"""Configuration is read locally. Tokens never appear in application logs."""
from dataclasses import dataclass
from pathlib import Path
import os
import re

ROOT = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z_][A-Z_0-9]*", key.strip()):
            raise ValueError("Проверьте формат файла .env: ИМЯ=значение")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Config:
    token: str
    admin_ids: frozenset[int]
    database: Path
    operator: str = "Команда проекта «Первые 100 дней»"

    @classmethod
    def from_env(cls):
        load_env(ROOT / ".env")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{30,}", token):
            raise ValueError("Добавьте TELEGRAM_BOT_TOKEN в telegram-bot/.env")
        try:
            admins = frozenset(int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip())
        except ValueError:
            raise ValueError("TELEGRAM_ADMIN_IDS должен содержать числовые ID через запятую") from None
        if not admins or any(x <= 0 for x in admins):
            raise ValueError("Добавьте TELEGRAM_ADMIN_IDS. Свой ID можно узнать командой /id")
        database = Path(os.getenv("BOT_DATABASE", str(ROOT / "data" / "bot.sqlite3")))
        if not database.is_absolute():
            database = ROOT / database
        return cls(token, admins, database, os.getenv("PROGRAM_OPERATOR", cls.operator))
