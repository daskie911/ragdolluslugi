"""
Обработка данных от Mini App (web_app_data).
Когда пользователь нажимает «Пополнить» в Mini App,
Mini App отправляет sendData → бот ловит и создаёт invoice.
"""
from __future__ import annotations

import json
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, LabeledPrice

from config import TOPUP_PACKAGES
from database import ensure_user
from keyboards.inline import back_to_menu_kb

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message, bot: Bot):
    """Обработка данных от Mini App."""
    user = message.from_user
    await ensure_user(user.id, user.username, user.first_name)

    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, AttributeError):
        await message.answer("❌ Ошибка данных от Mini App")
        return

    action = data.get("action")

    if action == "topup":
        # Пополнение стандартным пакетом
        key = data.get("key", "")
        stars_cost = data.get("stars_cost", 0)
        stars_get = data.get("stars_get", 0)

        if not stars_cost or not stars_get:
            await message.answer("❌ Некорректный пакет")
            return

        bonus = stars_get - stars_cost
        bonus_text = f" (+{bonus} бонус)" if bonus > 0 else ""

        try:
            await bot.send_invoice(
                chat_id=user.id,
                title=f"💰 Пополнение {stars_get} ⭐",
                description=f"Вы получите {stars_get} внутренних звёзд{bonus_text}",
                payload=f"topup|{key}|{stars_get}",
                currency="XTR",
                prices=[LabeledPrice(label=f"Пополнение {stars_get} ⭐", amount=stars_cost)],
            )
        except Exception as e:
            logger.error(f"Ошибка invoice из webapp: {e}")
            await message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

    elif action == "topup_custom":
        # Своя сумма
        amount = data.get("amount", 0)

        if not isinstance(amount, int) or amount < 1 or amount > 10000:
            await message.answer("❌ Некорректная сумма (1–10000)")
            return

        try:
            await bot.send_invoice(
                chat_id=user.id,
                title=f"💰 Пополнение {amount} ⭐",
                description=f"Вы получите {amount} внутренних звёзд",
                payload=f"topup|custom|{amount}",
                currency="XTR",
                prices=[LabeledPrice(label=f"Пополнение {amount} ⭐", amount=amount)],
            )
        except Exception as e:
            logger.error(f"Ошибка invoice custom из webapp: {e}")
            await message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

    else:
        await message.answer("❌ Неизвестное действие")
