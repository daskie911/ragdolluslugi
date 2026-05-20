"""
Обработчики оплаты. Только приватный чат.

Два потока:
1. ПОПОЛНЕНИЕ БАЛАНСА: topup → Telegram Stars invoice → successful_payment → баланс +N
2. ПОКУПКА УСЛУГИ: pay → проверка баланса → списание → применение услуги
"""
from __future__ import annotations

import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message,
    LabeledPrice, PreCheckoutQuery,
)
from aiogram.fsm.context import FSMContext

from config import SERVICES, DURATION_LABELS, GROUP_ID, TOPUP_PACKAGES
from handlers.user import OrderState
from database import (
    add_purchase, get_user_balance, add_balance, ensure_user,
)
from utils import format_stars
from keyboards.inline import back_to_menu_kb

import services as svc_module

logger = logging.getLogger(__name__)

# ── Роутер только для ПРИВАТНЫХ чатов ────────────────────────
router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


# ══════════════════════════════════════════════════════════════
#  ПОПОЛНЕНИЕ БАЛАНСА (Telegram Stars → внутренние ⭐)
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("topup:"))
async def topup_send_invoice(call: CallbackQuery, bot: Bot):
    key = call.data.split(":")[1]
    # "custom" обрабатывается в user.py, сюда не попадёт
    package = TOPUP_PACKAGES.get(key)
    if not package:
        await call.answer("Пакет не найден", show_alert=True)
        return

    stars_cost, stars_get = package
    bonus = stars_get - stars_cost
    bonus_text = f" (+{bonus} бонус)" if bonus > 0 else ""

    try:
        await bot.send_invoice(
            chat_id=call.from_user.id,
            title=f"💰 Пополнение {stars_get} ⭐",
            description=f"Вы получите {stars_get} внутренних звёзд{bonus_text}",
            payload=f"topup|{key}|{stars_get}",
            currency="XTR",
            prices=[LabeledPrice(label=f"Пополнение {stars_get} ⭐", amount=stars_cost)],
        )
        await call.answer()
    except Exception as e:
        logger.error(f"Ошибка invoice пополнения: {e}")
        await call.answer(f"Ошибка: {e}", show_alert=True)


# ── Pre-checkout ─────────────────────────────────────────────

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)


# ── Successful payment — пополняем баланс ────────────────────

@router.message(F.successful_payment)
async def process_successful_payment(message: Message, state: FSMContext, bot: Bot):
    payment = message.successful_payment
    payload = payment.invoice_payload

    user = message.from_user
    await ensure_user(user.id, user.username, user.first_name)

    if payload.startswith("topup|"):
        parts = payload.split("|")
        stars_get = int(parts[2]) if len(parts) > 2 else payment.total_amount

        new_balance = await add_balance(user.id, stars_get)

        await message.answer(
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"💎 Оплачено: {payment.total_amount} Telegram Stars\n"
            f"⭐ Зачислено: <b>{stars_get}</b> звёзд\n"
            f"💰 Новый баланс: <b>{format_stars(new_balance)}</b>",
            reply_markup=back_to_menu_kb(),
        )
    else:
        await message.answer(
            "✅ Платёж получен!",
            reply_markup=back_to_menu_kb(),
        )

    await state.clear()


# ══════════════════════════════════════════════════════════════
#  ПОКУПКА УСЛУГИ (с внутреннего баланса)
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("pay:"), OrderState.confirming)
async def pay_from_balance(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    service_key = data.get("service", "")
    price = data.get("price", 0)
    duration_key = data.get("duration", "once")
    target_id = data.get("target_id")
    text_data = data.get("text_data", "")
    photo_file_id = data.get("photo_file_id", "")
    msg_id = data.get("message_id")

    buyer_id = call.from_user.id

    balance = await get_user_balance(buyer_id)
    if balance < price:
        await call.answer(
            f"❌ Недостаточно звёзд!\n"
            f"Нужно: {price} ⭐, у вас: {balance} ⭐\n"
            f"Пополните баланс.",
            show_alert=True,
        )
        return

    new_balance = await add_balance(buyer_id, -price)

    svc_info = SERVICES.get(service_key, (service_key, "❓", ""))
    name, emoji, _ = svc_info
    chat_id = GROUP_ID

    await add_purchase(
        buyer_id=buyer_id,
        service=service_key,
        duration_key=duration_key,
        price_stars=price,
        target_id=target_id,
        payload=text_data or photo_file_id or (str(msg_id) if msg_id else None),
        telegram_charge=None,
    )

    result = "❓ Неизвестная услуга"

    try:
        if service_key == "mute" and target_id:
            result = await svc_module.apply_mute(
                bot, chat_id, target_id, buyer_id, duration_key
            )
        elif service_key == "ban" and target_id:
            result = await svc_module.apply_ban(
                bot, chat_id, target_id, buyer_id, duration_key
            )
        elif service_key == "unban" and target_id:
            result = await svc_module.apply_unban(
                bot, chat_id, target_id, buyer_id
            )
        elif service_key == "prefix" and target_id:
            result = await svc_module.apply_prefix(
                bot, chat_id, target_id, buyer_id, text_data, duration_key
            )
        elif service_key == "avatar" and photo_file_id:
            result = await svc_module.apply_avatar(
                bot, chat_id, buyer_id, photo_file_id, duration_key
            )
        elif service_key == "description" and text_data:
            result = await svc_module.apply_description(
                bot, chat_id, buyer_id, text_data, duration_key
            )
        elif service_key == "pin" and msg_id:
            result = await svc_module.apply_pin(
                bot, chat_id, buyer_id, msg_id, duration_key
            )
        elif service_key == "lock":
            result = await svc_module.apply_lock(
                bot, chat_id, buyer_id, duration_key
            )
    except Exception as e:
        logger.error(f"Ошибка при применении {service_key}: {e}")
        result = f"❌ Ошибка: {e}"
        await add_balance(buyer_id, price)
        new_balance = await get_user_balance(buyer_id)
        result += f"\n\n💰 Звёзды возвращены на баланс."

    if result.startswith("❌"):
        await add_balance(buyer_id, price)
        new_balance = await get_user_balance(buyer_id)
        result += f"\n\n💰 <b>{price}</b> ⭐ возвращены на баланс."

    dur_label = DURATION_LABELS.get(duration_key, duration_key)
    await call.message.edit_text(
        f"{'✅' if not result.startswith('❌') else '⚠️'} <b>Результат заказа</b>\n\n"
        f"{emoji} <b>{name}</b>\n"
        f"💰 Списано: {format_stars(price)}\n"
        f"{'🕐 Срок: ' + dur_label + chr(10) if duration_key != 'once' else ''}"
        f"💰 Баланс: <b>{format_stars(new_balance)}</b>\n\n"
        f"<b>Результат:</b>\n{result}",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()
    await state.clear()
