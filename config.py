"""
Конфигурация бота — загрузка переменных окружения и константы.
Цены сохраняются в prices.json и переживают перезапуск.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Основные настройки ──────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
GROUP_ID: int = int(os.getenv("GROUP_ID", "0"))
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

# ── Список админов (ID) ─────────────────────────────────────
_extra = os.getenv("ADMIN_IDS", "")
ADMINS: list[int] = [OWNER_ID] + [
    int(x.strip()) for x in _extra.split(",") if x.strip().isdigit()
]

# ── Пакеты пополнения баланса (Telegram Stars → внутренние ⭐) ──
TOPUP_PACKAGES: dict[str, tuple[int, int]] = {
    "topup_10":  (10,  10),
    "topup_25":  (25,  30),
    "topup_50":  (50,  65),
    "topup_100": (100, 140),
    "topup_250": (250, 375),
}

# ── Каталог услуг ───────────────────────────────────────────
SERVICES: dict[str, tuple[str, str, str]] = {
    "mute":        ("Мут",              "🔇", "Замутить пользователя в чате"),
    "ban":         ("Бан",              "🚫", "Забанить пользователя в чате"),
    "unban":       ("Разбан / Размут",  "✅", "Снять бан или мут пользователя"),
    "prefix":      ("Префикс",         "🏷", "Установить префикс перед именем"),
    "description": ("Описание чата",    "📝", "Изменить описание группы"),
    "pin":         ("Закреп сообщения", "📌", "Закрепить сообщение в чате"),
}

# ── Сроки (секунды) ─────────────────────────────────────────
DURATIONS: dict[str, int] = {
    "10m":     10 * 60,
    "30m":     30 * 60,
    "1h":      60 * 60,
    "3h":      3 * 60 * 60,
    "12h":     12 * 60 * 60,
    "24h":     24 * 60 * 60,
    "7d":      7 * 24 * 60 * 60,
    "30d":     30 * 24 * 60 * 60,
    "forever": 0,
}

DURATION_LABELS: dict[str, str] = {
    "10m":     "10 минут",
    "30m":     "30 минут",
    "1h":      "1 час",
    "3h":      "3 часа",
    "12h":     "12 часов",
    "24h":     "24 часа",
    "7d":      "7 дней",
    "30d":     "30 дней",
    "forever": "Навсегда",
}

# ── Дефолтные цены ──────────────────────────────────────────
_DEFAULT_PRICES: dict[str, dict[str, int]] = {
    "mute": {
        "10m": 1, "30m": 2, "1h": 3, "3h": 5,
        "12h": 8, "24h": 10, "7d": 25, "30d": 50, "forever": 100,
    },
    "ban": {
        "10m": 2, "30m": 3, "1h": 5, "3h": 8,
        "12h": 15, "24h": 20, "7d": 40, "30d": 75, "forever": 150,
    },
    "unban":       {"once": 5},
    "prefix": {
        "1h": 3, "3h": 5, "12h": 10, "24h": 15, "7d": 30, "30d": 60,
    },
    "description": {
        "1h": 5, "3h": 10, "12h": 20, "24h": 30, "7d": 60,
    },
    "pin": {
        "1h": 3, "3h": 5, "12h": 10, "24h": 15, "7d": 30,
    },
}

# ── Загрузка / сохранение цен из файла ──────────────────────
PRICES_FILE = Path("prices.json")


def _load_prices() -> dict[str, dict[str, int]]:
    if PRICES_FILE.exists():
        try:
            with open(PRICES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _DEFAULT_PRICES.copy()


def save_prices() -> None:
    try:
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(PRICES, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


PRICES: dict[str, dict[str, int]] = _load_prices()

# ── Категории услуг ─────────────────────────────────────────
NO_DURATION_SERVICES = {"unban"}
TARGET_SERVICES      = {"mute", "ban", "unban", "prefix"}
PHOTO_SERVICES       = set()
TEXT_SERVICES         = {"prefix", "description"}
FORWARD_SERVICES     = {"pin"}
