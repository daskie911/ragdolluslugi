"""
REST API для Mini App.
Полная покупка услуг прямо из Mini App — без выхода в бота.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import unquote, parse_qs

from aiohttp import web

from config import (
    BOT_TOKEN, SERVICES, PRICES, DURATION_LABELS,
    GROUP_ID, TOPUP_PACKAGES, TARGET_SERVICES,
    NO_DURATION_SERVICES, PHOTO_SERVICES, TEXT_SERVICES,
)
from database import (
    get_user, get_user_balance, ensure_user, add_balance,
    get_user_purchases, add_purchase, get_user_id_by_username,
)
from utils import format_stars

logger = logging.getLogger(__name__)

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")

_bot_instance = None

def set_bot(bot):
    global _bot_instance
    _bot_instance = bot


# ═══════════════════════════════════════════════════════════════
# Telegram initData — извлечение user (с валидацией и без)
# ═══════════════════════════════════════════════════════════════

def _extract_user_from_init_data(init_data: str) -> dict | None:
    """Извлечь user из initData БЕЗ проверки подписи (fallback)."""
    try:
        parsed = parse_qs(init_data)
        user_raw = parsed.get("user", [None])[0]
        if user_raw:
            return json.loads(unquote(user_raw))
    except Exception:
        pass
    return None


def _validate_init_data_strict(init_data: str, bot_token: str) -> dict | None:
    """Валидация initData с проверкой HMAC."""
    try:
        parsed = parse_qs(init_data)
        check_hash = parsed.get("hash", [None])[0]
        if not check_hash:
            return None

        data_pairs = []
        for key, values in parsed.items():
            if key != "hash":
                data_pairs.append(f"{key}={values[0]}")
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if computed_hash != check_hash:
            return None

        user_raw = parsed.get("user", [None])[0]
        if user_raw:
            return json.loads(unquote(user_raw))
        return None
    except Exception as e:
        logger.error(f"initData validation error: {e}")
        return None


def get_user_from_request(request: web.Request) -> dict | None:
    """
    Извлечь пользователя из запроса.
    Сначала пробует строгую валидацию, потом fallback.
    """
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data:
        return None

    # Строгая проверка
    user = _validate_init_data_strict(init_data, BOT_TOKEN)
    if user:
        return user

    # Fallback — извлекаем user без проверки подписи
    user = _extract_user_from_init_data(init_data)
    if user and user.get("id"):
        logger.warning(f"initData HMAC failed, using fallback for user {user.get('id')}")
        return user

    return None


# ═══════════════════════════════════════════════════════════════
# API endpoints
# ═══════════════════════════════════════════════════════════════

routes = web.RouteTableDef()


@routes.get("/api/me")
async def api_me(request: web.Request):
    tg_user = get_user_from_request(request)
    if not tg_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    user_id = tg_user["id"]
    await ensure_user(user_id, tg_user.get("username"), tg_user.get("first_name"))

    balance = await get_user_balance(user_id)
    purchases = await get_user_purchases(user_id, limit=20)

    return web.json_response({
        "user_id": user_id,
        "username": tg_user.get("username"),
        "first_name": tg_user.get("first_name"),
        "balance": balance,
        "purchases_count": len(purchases),
        "purchases": purchases,
    })


@routes.get("/api/services")
async def api_services(request: web.Request):
    result = {}
    for key, (name, emoji, desc) in SERVICES.items():
        prices = PRICES.get(key, {})
        price_list = []
        for dur_key, price in prices.items():
            dur_label = DURATION_LABELS.get(dur_key, dur_key)
            price_list.append({
                "duration_key": dur_key,
                "duration_label": dur_label,
                "price": price,
            })

        needs_target = key in TARGET_SERVICES
        needs_text = key in TEXT_SERVICES and key != "prefix"
        needs_photo = key in PHOTO_SERVICES
        no_duration = key in NO_DURATION_SERVICES

        result[key] = {
            "name": name, "emoji": emoji, "description": desc,
            "prices": price_list,
            "needs_target": needs_target,
            "needs_text": needs_text,
            "needs_photo": needs_photo,
            "no_duration": no_duration,
        }
    return web.json_response(result)


@routes.get("/api/topup_packages")
async def api_topup_list(request: web.Request):
    packages = []
    for key, (cost, get) in TOPUP_PACKAGES.items():
        bonus = get - cost
        packages.append({"key": key, "stars_cost": cost, "stars_get": get, "bonus": bonus})
    return web.json_response(packages)


@routes.get("/api/history")
async def api_history(request: web.Request):
    tg_user = get_user_from_request(request)
    if not tg_user:
        return web.json_response({"error": "unauthorized"}, status=401)

    purchases = await get_user_purchases(tg_user["id"], limit=50)
    for p in purchases:
        svc_info = SERVICES.get(p.get("service", ""), ("?", "?", "?"))
        p["service_name"] = svc_info[0]
        p["service_emoji"] = svc_info[1]
        dur_key = p.get("duration_key", "")
        p["duration_label"] = DURATION_LABELS.get(dur_key, dur_key)

    return web.json_response(purchases)


@routes.post("/api/buy")
async def api_buy(request: web.Request):
    global _bot_instance

    tg_user = get_user_from_request(request)
    if not tg_user:
        return web.json_response({"ok": False, "error": "Не удалось авторизоваться. Откройте через Telegram."}, status=200)

    data = await request.json()
    service_key = data.get("service", "")
    duration_key = data.get("duration_key", "once")
    target_raw = data.get("target", "")
    text_data = data.get("text", "")

    if service_key not in SERVICES:
        return web.json_response({"ok": False, "error": "Неизвестная услуга"})

    prices = PRICES.get(service_key, {})
    price = prices.get(duration_key)
    if price is None:
        return web.json_response({"ok": False, "error": "Неверный срок"})

    user_id = tg_user["id"]
    balance = await get_user_balance(user_id)

    if balance < price:
        return web.json_response({
            "ok": False,
            "error": "insufficient_balance",
            "balance": balance, "price": price,
        })

    if not _bot_instance:
        return web.json_response({"ok": False, "error": "Бот не инициализирован"})

    bot = _bot_instance

    # Резолв цели
    target_id = None
    if service_key in TARGET_SERVICES:
        if not target_raw:
            return web.json_response({"ok": False, "error": "Укажите пользователя"})

        clean = target_raw.strip().lstrip("@")
        if clean.isdigit():
            target_id = int(clean)
        else:
            target_id = await get_user_id_by_username(clean)
            if not target_id:
                try:
                    chat = await bot.get_chat(f"@{clean}")
                    target_id = chat.id
                except Exception:
                    pass

        if not target_id:
            return web.json_response({"ok": False, "error": f"Пользователь @{clean} не найден."})

        if target_id == user_id:
            return web.json_response({"ok": False, "error": "Нельзя применить к самому себе"})

        me = await bot.get_me()
        if target_id == me.id:
            return web.json_response({"ok": False, "error": "Нельзя применить к боту"})

        if service_key in ("mute", "ban"):
            try:
                from aiogram.types import ChatMemberAdministrator, ChatMemberOwner
                member = await bot.get_chat_member(GROUP_ID, target_id)
                if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
                    return web.json_response({"ok": False, "error": "Нельзя применить к администратору"})
            except Exception:
                pass

    if service_key == "prefix":
        if not text_data:
            return web.json_response({"ok": False, "error": "Укажите текст префикса"})
        if len(text_data) > 16:
            return web.json_response({"ok": False, "error": "Максимум 16 символов"})

    if service_key == "description":
        if not text_data:
            return web.json_response({"ok": False, "error": "Укажите текст описания"})

    # === Списание ===
    new_balance = await add_balance(user_id, -price)

    # === Применение ===
    import services as svc_module

    result = "❓"
    try:
        if service_key == "mute" and target_id:
            result = await svc_module.apply_mute(bot, GROUP_ID, target_id, user_id, duration_key)
        elif service_key == "ban" and target_id:
            result = await svc_module.apply_ban(bot, GROUP_ID, target_id, user_id, duration_key)
        elif service_key == "unban" and target_id:
            result = await svc_module.apply_unban(bot, GROUP_ID, target_id, user_id)
        elif service_key == "prefix" and target_id:
            result = await svc_module.apply_prefix(bot, GROUP_ID, target_id, user_id, text_data, duration_key)
        elif service_key == "description":
            result = await svc_module.apply_description(bot, GROUP_ID, user_id, text_data, duration_key)
        elif service_key == "pin":
            msg_id = data.get("message_id")
            if msg_id:
                result = await svc_module.apply_pin(bot, GROUP_ID, user_id, int(msg_id), duration_key)
            else:
                result = "❌ Укажите ID сообщения"
    except Exception as e:
        logger.error(f"Ошибка применения {service_key}: {e}")
        result = f"❌ Ошибка: {e}"

    if result.startswith("❌"):
        await add_balance(user_id, price)
        new_balance = await get_user_balance(user_id)
        return web.json_response({
            "ok": False, "error": result,
            "balance": new_balance, "refunded": True,
        })

    await add_purchase(
        buyer_id=user_id, service=service_key,
        duration_key=duration_key, price_stars=price,
        target_id=target_id, payload=text_data or None,
        telegram_charge=None,
    )

    svc_info = SERVICES.get(service_key, (service_key, "?", "?"))
    dur_label = DURATION_LABELS.get(duration_key, duration_key)

    return web.json_response({
        "ok": True, "result": result,
        "service_name": svc_info[0], "service_emoji": svc_info[1],
        "duration_label": dur_label,
        "price": price, "balance": new_balance,
    })


@routes.post("/api/topup")
async def api_topup_invoice(request: web.Request):
    global _bot_instance

    tg_user = get_user_from_request(request)
    if not tg_user:
        return web.json_response({"ok": False, "error": "Не удалось авторизоваться. Откройте через Telegram."})

    if not _bot_instance:
        return web.json_response({"ok": False, "error": "Бот не инициализирован"})

    data = await request.json()
    key = data.get("key", "")
    stars_cost = data.get("stars_cost", 0)
    stars_get = data.get("stars_get", 0)

    if not stars_cost or not stars_get:
        return web.json_response({"ok": False, "error": "Некорректные данные"})

    bot = _bot_instance
    user_id = tg_user["id"]

    bonus = stars_get - stars_cost
    bonus_text = f" (+{bonus} бонус)" if bonus > 0 else ""

    try:
        from aiogram.types import LabeledPrice
        await bot.send_invoice(
            chat_id=user_id,
            title=f"💰 Пополнение {stars_get} ⭐",
            description=f"Вы получите {stars_get} внутренних звёзд{bonus_text}",
            payload=f"topup|{key}|{stars_get}",
            currency="XTR",
            prices=[LabeledPrice(label=f"Пополнение {stars_get} ⭐", amount=stars_cost)],
        )
        return web.json_response({"ok": True, "message": "Счёт отправлен в чат"})
    except Exception as e:
        logger.error(f"Ошибка topup invoice: {e}")
        return web.json_response({"ok": False, "error": f"Ошибка: {e}"})


# ═══════════════════════════════════════════════════════════════
# Статика
# ═══════════════════════════════════════════════════════════════

async def serve_webapp(request: web.Request):
    return web.FileResponse(os.path.join(WEBAPP_DIR, "index.html"))


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_routes(routes)
    app.router.add_get("/", serve_webapp)
    app.router.add_get("/webapp", serve_webapp)
    app.router.add_get("/webapp/", serve_webapp)
    if os.path.isdir(WEBAPP_DIR):
        app.router.add_static("/webapp/", WEBAPP_DIR, show_index=True)
    return app


async def start_api():
    port = int(os.getenv("PORT", "8080"))
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ API запущен на порту {port}")
    return runner
