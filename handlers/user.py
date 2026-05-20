"""
Обработчики пользовательских команд и навигации.
/start, меню, баланс, пополнение, выбор услуги, FSM-ввод данных.

ВАЖНО: все хендлеры работают ТОЛЬКО в приватном чате (F.chat.type == "private").
"""
from __future__ import annotations

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    SERVICES, PRICES, DURATION_LABELS, GROUP_ID,
    NO_DURATION_SERVICES, TARGET_SERVICES, PHOTO_SERVICES,
    TEXT_SERVICES, FORWARD_SERVICES,
)
from keyboards.inline import (
    main_menu_kb, services_kb, durations_kb, confirm_kb,
    cancel_kb, back_to_menu_kb, topup_kb,
)
from utils import resolve_user_id, format_stars, user_is_admin
from database import get_user_purchases, ensure_user, get_user_balance

logger = logging.getLogger(__name__)

# ── Роутер только для ПРИВАТНЫХ чатов ────────────────────────
router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


# ── FSM-состояния ────────────────────────────────────────────

class OrderState(StatesGroup):
    choosing_service = State()
    choosing_duration = State()
    waiting_target = State()
    waiting_text = State()
    waiting_photo = State()
    waiting_forward = State()
    confirming = State()
    waiting_custom_topup = State()


# ── /start ───────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    await ensure_user(user.id, user.username, user.first_name)

    balance = await get_user_balance(user.id)
    await message.answer(
        f"👋 <b>Добро пожаловать в магазин услуг!</b>\n\n"
        f"Здесь вы можете купить различные услуги для группы\n"
        f"💰 Ваш баланс: <b>{format_stars(balance)}</b>\n\n"
        f"Выберите действие:",
        reply_markup=main_menu_kb(),
    )


# ── Главное меню ─────────────────────────────────────────────

@router.callback_query(F.data == "menu:main")
async def menu_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = call.from_user
    await ensure_user(user.id, user.username, user.first_name)

    balance = await get_user_balance(user.id)
    await call.message.edit_text(
        f"🏠 <b>Главное меню</b>\n\n"
        f"💰 Баланс: <b>{format_stars(balance)}</b>\n\n"
        f"Выберите действие:",
        reply_markup=main_menu_kb(),
    )
    await call.answer()


# ── 👛 Мой баланс ────────────────────────────────────────────

@router.callback_query(F.data == "menu:balance")
async def menu_balance(call: CallbackQuery):
    balance = await get_user_balance(call.from_user.id)
    await call.message.edit_text(
        f"👛 <b>Ваш баланс</b>\n\n"
        f"⭐ <b>{balance}</b> звёзд\n\n"
        f"Пополнить баланс можно через Telegram Stars.\n"
        f"Звёзды используются для покупки услуг.",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


# ── 💰 Пополнить баланс ──────────────────────────────────────

@router.callback_query(F.data == "menu:topup")
async def menu_topup(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance = await get_user_balance(call.from_user.id)
    await call.message.edit_text(
        f"💰 <b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{format_stars(balance)}</b>\n\n"
        f"Выберите пакет или введите свою сумму.\n"
        f"Оплата через Telegram Stars 💎\n"
        f"Чем больше пакет — тем больше бонус! 🎁",
        reply_markup=topup_kb(),
    )
    await call.answer()


# ── ✏️ Своя сумма пополнения ─────────────────────────────────

@router.callback_query(F.data == "topup:custom")
async def topup_custom_prompt(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.waiting_custom_topup)
    await call.message.edit_text(
        "✏️ <b>Своя сумма пополнения</b>\n\n"
        "Введите количество Telegram Stars, которое хотите задонатить.\n\n"
        "Минимум: <b>1</b>, максимум: <b>10000</b>\n"
        "Вы получите столько же внутренних ⭐\n\n"
        "Например: <code>42</code>",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(OrderState.waiting_custom_topup)
async def topup_custom_process(message: Message, state: FSMContext, bot: Bot):
    text = (message.text or "").strip()

    if not text.isdigit():
        await message.answer(
            "❌ Введите целое число.\nНапример: <code>42</code>",
            reply_markup=cancel_kb(),
        )
        return

    amount = int(text)
    if amount < 1:
        await message.answer("❌ Минимум — <b>1</b> Star.", reply_markup=cancel_kb())
        return
    if amount > 10000:
        await message.answer("❌ Максимум — <b>10000</b> Stars.", reply_markup=cancel_kb())
        return

    try:
        from aiogram.types import LabeledPrice
        await bot.send_invoice(
            chat_id=message.from_user.id,
            title=f"💰 Пополнение {amount} ⭐",
            description=f"Вы получите {amount} внутренних звёзд",
            payload=f"topup|custom|{amount}",
            currency="XTR",
            prices=[LabeledPrice(label=f"Пополнение {amount} ⭐", amount=amount)],
        )
    except Exception as e:
        logger.error(f"Ошибка invoice custom topup: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

    await state.clear()


# ── ℹ️ Помощь ────────────────────────────────────────────────

@router.callback_query(F.data == "menu:help")
async def menu_help(call: CallbackQuery):
    text = (
        "ℹ️ <b>Помощь</b>\n\n"
        "Этот бот позволяет покупать услуги для группы.\n\n"
        "<b>Как это работает:</b>\n"
        "1️⃣ Пополните баланс через Telegram Stars\n"
        "2️⃣ Выберите услугу\n"
        "3️⃣ Укажите срок (если нужно)\n"
        "4️⃣ Укажите цель (пользователь, текст, фото…)\n"
        "5️⃣ Оплатите с баланса ⭐\n"
        "6️⃣ Бот автоматически применит услугу!\n\n"
        "После истечения срока услуга автоматически отменяется.\n\n"
        "⚠️ Бот должен быть администратором в группе."
    )
    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()


# ── 📜 История покупок ───────────────────────────────────────

@router.callback_query(F.data == "menu:history")
async def menu_history(call: CallbackQuery):
    purchases = await get_user_purchases(call.from_user.id)
    if not purchases:
        text = "📜 <b>Мои покупки</b>\n\nУ вас пока нет покупок."
    else:
        lines = ["📜 <b>Мои покупки</b>\n"]
        for p in purchases[:15]:
            svc_info = SERVICES.get(p["service"], (p["service"], "❓", ""))
            lines.append(
                f"• {svc_info[1]} {svc_info[0]} — "
                f"{format_stars(p['price_stars'])}"
            )
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=back_to_menu_kb())
    await call.answer()


# ── 🛒 Список услуг ──────────────────────────────────────────

@router.callback_query(F.data == "menu:services")
async def menu_services(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance = await get_user_balance(call.from_user.id)
    text = f"🛒 <b>Выберите услугу:</b>\n\n💰 Баланс: <b>{format_stars(balance)}</b>\n\n"
    for key, (name, emoji, desc) in SERVICES.items():
        text += f"{emoji} <b>{name}</b> — {desc}\n"

    await call.message.edit_text(text, reply_markup=services_kb())
    await call.answer()


# ── Выбор конкретной услуги ──────────────────────────────────

@router.callback_query(F.data.startswith("svc:"))
async def select_service(call: CallbackQuery, state: FSMContext):
    service_key = call.data.split(":")[1]
    svc_info = SERVICES.get(service_key)
    if not svc_info:
        await call.answer("Услуга не найдена", show_alert=True)
        return

    name, emoji, desc = svc_info
    await state.update_data(service=service_key)

    if service_key in NO_DURATION_SERVICES:
        prices = PRICES.get(service_key, {})
        price = prices.get("once", 1)
        await state.update_data(duration="once", price=price)
        await _ask_next_input(call, state, service_key)
    else:
        text = (
            f"{emoji} <b>{name}</b>\n\n"
            f"{desc}\n\n"
            f"Выберите срок:"
        )
        await call.message.edit_text(text, reply_markup=durations_kb(service_key))

    await call.answer()


# ── Выбор срока ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("dur:"))
async def select_duration(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    service_key = parts[1]
    duration_key = parts[2]

    prices = PRICES.get(service_key, {})
    price = prices.get(duration_key, 1)

    await state.update_data(duration=duration_key, price=price)
    await _ask_next_input(call, state, service_key)
    await call.answer()


# ── Логика перехода к нужному вводу ──────────────────────────

async def _ask_next_input(call: CallbackQuery, state: FSMContext, service_key: str):
    if service_key in TARGET_SERVICES:
        await state.set_state(OrderState.waiting_target)
        await call.message.edit_text(
            "👤 <b>Введите username или ID пользователя:</b>\n\n"
            "Например: <code>@username</code> или <code>123456789</code>",
            reply_markup=cancel_kb(),
        )
    elif service_key in PHOTO_SERVICES:
        await state.set_state(OrderState.waiting_photo)
        await call.message.edit_text(
            "🖼 <b>Отправьте фото</b>, которое станет аватаркой группы:",
            reply_markup=cancel_kb(),
        )
    elif service_key in TEXT_SERVICES:
        await state.set_state(OrderState.waiting_text)
        await call.message.edit_text(
            "📝 <b>Введите новый текст описания группы:</b>",
            reply_markup=cancel_kb(),
        )
    elif service_key in FORWARD_SERVICES:
        await state.set_state(OrderState.waiting_forward)
        await call.message.edit_text(
            "📌 <b>Перешлите сообщение</b> из группы, которое нужно закрепить.\n\n"
            "Или отправьте <b>ID сообщения</b> (число):",
            reply_markup=cancel_kb(),
        )
    else:
        await _show_confirmation(call.message, state)


# ── Ввод target ──────────────────────────────────────────────

@router.message(OrderState.waiting_target)
async def input_target(message: Message, state: FSMContext, bot: Bot):
    raw = message.text or ""
    if not raw.strip():
        await message.answer("❌ Пожалуйста, введите username или ID.")
        return

    target_id = await resolve_user_id(bot, raw, GROUP_ID)
    if target_id is None:
        await message.answer(
            "❌ Не удалось найти пользователя.\n\n"
            "Убедитесь, что вы ввели правильный @username или числовой ID.\n"
            "💡 <i>Пользователь должен хотя бы раз написать боту /start, "
            "чтобы бот знал его username.</i>"
        )
        return

    data = await state.get_data()
    service_key = data.get("service", "")

    if service_key in ("mute", "ban"):
        is_adm = await user_is_admin(bot, GROUP_ID, target_id)
        if is_adm:
            await message.answer(
                "⛔ <b>Этот пользователь — администратор группы.</b>\n\n"
                "Администраторов нельзя замутить или забанить.\n"
                "Выберите другого пользователя.",
                reply_markup=cancel_kb(),
            )
            return

    me = await bot.get_me()
    if target_id == me.id:
        await message.answer("🤖 Нельзя применить услугу к самому боту!",
                             reply_markup=cancel_kb())
        return

    await state.update_data(target_id=target_id)

    if service_key == "prefix":
        await state.set_state(OrderState.waiting_text)
        await message.answer(
            "🏷 <b>Введите текст префикса</b> (до 16 символов):",
            reply_markup=cancel_kb(),
        )
    else:
        await _show_confirmation(message, state)


# ── Ввод текста ──────────────────────────────────────────────

@router.message(OrderState.waiting_text)
async def input_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Пожалуйста, введите текст.")
        return
    await state.update_data(text_data=text)
    await _show_confirmation(message, state)


# ── Ввод фото ────────────────────────────────────────────────

@router.message(OrderState.waiting_photo, F.photo)
async def input_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    await _show_confirmation(message, state)

@router.message(OrderState.waiting_photo)
async def input_photo_invalid(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте именно фото (не файл).")


# ── Ввод message_id ──────────────────────────────────────────

@router.message(OrderState.waiting_forward)
async def input_forward(message: Message, state: FSMContext):
    msg_id: int | None = None
    if message.text and message.text.strip().isdigit():
        msg_id = int(message.text.strip())

    if msg_id is None:
        await message.answer(
            "❌ Пожалуйста, отправьте <b>числовой ID сообщения</b> из группы.\n"
            "Чтобы узнать ID — нажмите правой кнопкой на сообщение → "
            "«Копировать ссылку» → число в конце ссылки."
        )
        return

    await state.update_data(message_id=msg_id)
    await _show_confirmation(message, state)


# ── Подтверждение заказа ─────────────────────────────────────

async def _show_confirmation(target: Message, state: FSMContext):
    data = await state.get_data()
    service_key = data.get("service", "")
    duration_key = data.get("duration", "")
    price = data.get("price", 0)

    svc_info = SERVICES.get(service_key, (service_key, "❓", ""))
    name, emoji, _ = svc_info
    dur_label = DURATION_LABELS.get(duration_key, duration_key)

    lines = [
        f"📋 <b>Подтверждение заказа</b>\n",
        f"{emoji} <b>Услуга:</b> {name}",
    ]
    if duration_key != "once":
        lines.append(f"🕐 <b>Срок:</b> {dur_label}")
    if "target_id" in data:
        lines.append(f"👤 <b>Цель:</b> <code>{data['target_id']}</code>")
    if "text_data" in data:
        txt = data["text_data"]
        lines.append(f"📝 <b>Текст:</b> {txt[:50]}{'…' if len(txt) > 50 else ''}")
    if "photo_file_id" in data:
        lines.append("🖼 <b>Фото:</b> прикреплено")
    if "message_id" in data:
        lines.append(f"📌 <b>Сообщение:</b> #{data['message_id']}")

    lines.append(f"\n💰 <b>Стоимость:</b> {format_stars(price)}")
    lines.append("\nНажмите <b>«Оплатить с баланса»</b> для покупки:")

    await state.set_state(OrderState.confirming)
    await target.answer(
        "\n".join(lines),
        reply_markup=confirm_kb(service_key),
    )


# ── Отмена ───────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_order(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "❌ Заказ отменён.",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()
