"""
Вспомогательные утилиты.
"""
from __future__ import annotations
import re
import logging
from aiogram import Bot
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner

from database import get_user_id_by_username

logger = logging.getLogger(__name__)


async def resolve_user_id(bot: Bot, raw: str, chat_id: int) -> int | None:
    raw = raw.strip().lstrip("@")

    if re.fullmatch(r"-?\d+", raw):
        return int(raw)

    cached = await get_user_id_by_username(raw)
    if cached:
        return cached

    try:
        chat = await bot.get_chat(f"@{raw}")
        return chat.id
    except Exception:
        pass

    return None


async def bot_is_admin(bot: Bot, chat_id: int) -> bool:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


async def user_is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


async def user_is_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in ("left", "kicked")
    except Exception:
        return False


def format_stars(amount: int) -> str:
    return f"{amount} ⭐"
