"""
Инлайн-клавиатуры для бота.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SERVICES, PRICES, DURATION_LABELS, TOPUP_PACKAGES
from utils import format_stars


# ═══════════════════════════════════════════════════════════════
#  Пользовательские клавиатуры
# ═══════════════════════════════════════════════════════════════

def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Услуги", callback_data="menu:services"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="menu:topup"),
    )
    builder.row(
        InlineKeyboardButton(text="👛 Мой баланс", callback_data="menu:balance"),
        InlineKeyboardButton(text="📜 Мои покупки", callback_data="menu:history"),
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
    )
    return builder.as_markup()


def services_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, (name, emoji, _desc) in SERVICES.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} {name}",
                callback_data=f"svc:{key}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")
    )
    return builder.as_markup()


def durations_kb(service_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prices = PRICES.get(service_key, {})
    for dur_key, price in prices.items():
        label = DURATION_LABELS.get(dur_key, dur_key)
        builder.row(
            InlineKeyboardButton(
                text=f"🕐 {label} — {format_stars(price)}",
                callback_data=f"dur:{service_key}:{dur_key}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ К услугам", callback_data="menu:services")
    )
    return builder.as_markup()


def confirm_kb(service_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💰 Оплатить с баланса",
            callback_data=f"pay:{service_key}",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    )
    return builder.as_markup()


def topup_kb() -> InlineKeyboardMarkup:
    """Пакеты пополнения + кнопка своей суммы."""
    builder = InlineKeyboardBuilder()
    for key, (stars_cost, stars_get) in TOPUP_PACKAGES.items():
        bonus = stars_get - stars_cost
        bonus_text = f" (+{bonus} бонус)" if bonus > 0 else ""
        builder.row(
            InlineKeyboardButton(
                text=f"💳 {stars_cost} Stars → {stars_get} ⭐{bonus_text}",
                callback_data=f"topup:{key}",
            )
        )
    # Кнопка «Своя сумма»
    builder.row(
        InlineKeyboardButton(
            text="✏️ Своя сумма",
            callback_data="topup:custom",
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")
    )
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"),
    )
    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════
#  Админские клавиатуры
# ═══════════════════════════════════════════════════════════════

def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
    )
    builder.row(
        InlineKeyboardButton(text="👥 Все пользователи", callback_data="adm:users"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Выдать звёзды", callback_data="adm:give_stars"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Изменить цены", callback_data="adm:prices"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="menu:main"),
    )
    return builder.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 Назад в админку", callback_data="adm:menu"),
    )
    return builder.as_markup()


def admin_prices_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, (name, emoji, _desc) in SERVICES.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{emoji} {name}",
                callback_data=f"adm:price:{key}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад в админку", callback_data="adm:menu"),
    )
    return builder.as_markup()
