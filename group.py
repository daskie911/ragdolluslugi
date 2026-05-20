"""
Обработчик сообщений в группе.
Главная задача: кэшировать username → user_id всех,
кто пишет в группу.
"""
from __future__ import annotations

import logging
from aiogram import Router, F
from aiogram.types import Message

from database import ensure_user

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def cache_group_user(message: Message):
    user = message.from_user
    if user and not user.is_bot:
        await ensure_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
