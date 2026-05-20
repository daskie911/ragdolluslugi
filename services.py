"""
Логика применения и отмены каждой услуги.
Каждая функция принимает bot + нужные параметры и выполняет действие в Telegram.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

from aiogram import Bot
from aiogram.types import ChatPermissions, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import DURATIONS, GROUP_ID
from database import add_active_service, deactivate_service

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Вспомогательные
# ─────────────────────────────────────────────────────────────

def _until_date(duration_key: str) -> datetime | None:
    seconds = DURATIONS.get(duration_key, 0)
    if seconds == 0:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _expires_ts(duration_key: str) -> int:
    seconds = DURATIONS.get(duration_key, 0)
    if seconds == 0:
        return 0
    return int(time.time()) + seconds


# ─────────────────────────────────────────────────────────────
# Применение услуг
# ─────────────────────────────────────────────────────────────

async def apply_mute(
    bot: Bot, chat_id: int, target_id: int, buyer_id: int, duration_key: str
) -> str:
    until = _until_date(duration_key)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False,
                can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False,
            ),
            until_date=until,
        )
    except TelegramBadRequest as e:
        return f"❌ Не удалось замутить: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав администратора в группе!"

    await add_active_service(
        "mute", chat_id, target_id, buyer_id, None, _expires_ts(duration_key)
    )
    return f"🔇 Пользователь `{target_id}` замучен!"


async def apply_ban(
    bot: Bot, chat_id: int, target_id: int, buyer_id: int, duration_key: str
) -> str:
    until = _until_date(duration_key)
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=target_id, until_date=until)
    except TelegramBadRequest as e:
        return f"❌ Не удалось забанить: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав администратора!"

    await add_active_service(
        "ban", chat_id, target_id, buyer_id, None, _expires_ts(duration_key)
    )
    return f"🚫 Пользователь `{target_id}` забанен!"


async def apply_unban(
    bot: Bot, chat_id: int, target_id: int, buyer_id: int
) -> str:
    try:
        await bot.unban_chat_member(chat_id=chat_id, user_id=target_id, only_if_banned=True)
    except TelegramBadRequest:
        pass
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_audios=True,
                can_send_documents=True, can_send_photos=True,
                can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True,
            ),
        )
    except Exception:
        pass
    return f"✅ Пользователь `{target_id}` разбанен / размучен!"


async def apply_prefix(
    bot: Bot, chat_id: int, target_id: int, buyer_id: int,
    prefix_text: str, duration_key: str
) -> str:
    try:
        # Шаг 1: Повышаем до админа с МИНИМАЛЬНЫМ правом
        # can_manage_chat=True ОБЯЗАТЕЛЬНО — иначе Telegram не считает юзера админом
        await bot.promote_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            can_manage_chat=True,       # ← ОБЯЗАТЕЛЬНО True!
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_post_stories=False,
            can_edit_stories=False,
            can_delete_stories=False,
            can_pin_messages=False,
        )

        # Шаг 2: Небольшая пауза — Telegram нужно время на обработку
        await asyncio.sleep(0.5)

        # Шаг 3: Устанавливаем кастомный титул
        await bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=target_id,
            custom_title=prefix_text[:16],  # макс 16 символов
        )
    except TelegramBadRequest as e:
        return f"❌ Не удалось установить префикс: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав для назначения префикса!"

    await add_active_service(
        "prefix", chat_id, target_id, buyer_id, prefix_text, _expires_ts(duration_key)
    )
    return f"🏷 Префикс «{prefix_text}» установлен для пользователя `{target_id}`!"


async def apply_avatar(
    bot: Bot, chat_id: int, buyer_id: int, file_id: str, duration_key: str
) -> str:
    try:
        file = await bot.get_file(file_id)
        bio = BytesIO()
        await bot.download_file(file.file_path, bio)
        bio.seek(0)
        photo = BufferedInputFile(bio.read(), filename="avatar.jpg")
        await bot.set_chat_photo(chat_id=chat_id, photo=photo)
    except TelegramBadRequest as e:
        return f"❌ Не удалось сменить аватарку: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав для смены аватарки!"

    await add_active_service(
        "avatar", chat_id, None, buyer_id, file_id, _expires_ts(duration_key)
    )
    return "🖼 Аватарка группы обновлена!"


async def apply_description(
    bot: Bot, chat_id: int, buyer_id: int, text: str, duration_key: str
) -> str:
    try:
        await bot.set_chat_description(chat_id=chat_id, description=text[:255])
    except TelegramBadRequest as e:
        return f"❌ Не удалось сменить описание: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав для смены описания!"

    await add_active_service(
        "description", chat_id, None, buyer_id, text, _expires_ts(duration_key)
    )
    return "📝 Описание группы обновлено!"


async def apply_pin(
    bot: Bot, chat_id: int, buyer_id: int, message_id: int, duration_key: str
) -> str:
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as e:
        return f"❌ Не удалось закрепить: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав для закрепа!"

    await add_active_service(
        "pin", chat_id, None, buyer_id, str(message_id), _expires_ts(duration_key)
    )
    return "📌 Сообщение закреплено!"


async def apply_lock(
    bot: Bot, chat_id: int, buyer_id: int, duration_key: str
) -> str:
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False,
                can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False,
            ),
        )
    except TelegramBadRequest as e:
        return f"❌ Не удалось заблокировать чат: {e.message}"
    except TelegramForbiddenError:
        return "❌ У бота нет прав!"

    await add_active_service(
        "lock", chat_id, None, buyer_id, None, _expires_ts(duration_key)
    )
    return "🔒 Чат заблокирован!"


# ─────────────────────────────────────────────────────────────
# Отмена услуг (вызывается по расписанию)
# ─────────────────────────────────────────────────────────────

async def revert_service(bot: Bot, service: dict) -> None:
    """Откатывает истёкшую услугу."""
    svc = service["service"]
    chat_id = service["chat_id"]
    target_id = service.get("target_id")
    svc_id = service["id"]

    try:
        if svc == "mute" and target_id:
            await bot.restrict_chat_member(
                chat_id=chat_id, user_id=target_id,
                permissions=ChatPermissions(
                    can_send_messages=True, can_send_audios=True,
                    can_send_documents=True, can_send_photos=True,
                    can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True,
                ),
            )
            logger.info(f"Авто-размут: user {target_id} в чате {chat_id}")

        elif svc == "ban" and target_id:
            await bot.unban_chat_member(chat_id=chat_id, user_id=target_id, only_if_banned=True)
            logger.info(f"Авто-разбан: user {target_id} в чате {chat_id}")

        elif svc == "prefix" and target_id:
            # Сначала очищаем титул, потом снимаем админку
            try:
                await bot.set_chat_administrator_custom_title(
                    chat_id=chat_id, user_id=target_id, custom_title=""
                )
            except Exception:
                pass
            try:
                # Снимаем админку (понижаем обратно)
                await bot.promote_chat_member(
                    chat_id=chat_id, user_id=target_id,
                    can_manage_chat=False,
                    can_delete_messages=False,
                    can_manage_video_chats=False,
                    can_restrict_members=False,
                    can_promote_members=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_post_stories=False,
                    can_edit_stories=False,
                    can_delete_stories=False,
                    can_pin_messages=False,
                )
            except Exception:
                pass
            logger.info(f"Авто-снятие префикса + админки: user {target_id}")

        elif svc == "avatar":
            try:
                await bot.delete_chat_photo(chat_id=chat_id)
            except Exception:
                pass
            logger.info(f"Авто-сброс аватарки чата {chat_id}")

        elif svc == "description":
            try:
                await bot.set_chat_description(chat_id=chat_id, description="")
            except Exception:
                pass
            logger.info(f"Авто-сброс описания чата {chat_id}")

        elif svc == "pin":
            msg_id = service.get("payload")
            if msg_id:
                try:
                    await bot.unpin_chat_message(chat_id=chat_id, message_id=int(msg_id))
                except Exception:
                    pass
            logger.info(f"Авто-открепление сообщения в чате {chat_id}")

        elif svc == "lock":
            await bot.set_chat_permissions(
                chat_id=chat_id,
                permissions=ChatPermissions(
                    can_send_messages=True, can_send_audios=True,
                    can_send_documents=True, can_send_photos=True,
                    can_send_videos=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True,
                    can_send_other_messages=True, can_add_web_page_previews=True,
                ),
            )
            logger.info(f"Авто-разблокировка чата {chat_id}")

    except Exception as e:
        logger.error(f"Ошибка при откате услуги #{svc_id}: {e}")

    await deactivate_service(svc_id)
