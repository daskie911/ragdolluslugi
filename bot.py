"""
Точка входа — запуск бота + API для Mini App.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from database import init_db, get_expired_services
from services import revert_service
from handlers import user, payments, admin
from handlers.group import router as group_router
from handlers.webapp_handler import router as webapp_router
from api import start_api, set_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def check_expired(bot: Bot) -> None:
    try:
        expired = await get_expired_services()
        for svc in expired:
            logger.info(f"Откат услуги #{svc['id']} ({svc['service']})")
            await revert_service(bot, svc)
    except Exception as e:
        logger.error(f"Ошибка проверки истёкших: {e}")


async def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ Укажите BOT_TOKEN в файле .env!")
        return

    await init_db()
    logger.info("✅ База данных инициализирована")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Передаём bot в API чтобы Mini App мог применять услуги
    set_bot(bot)

    # Запускаем API
    api_runner = await start_api()

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(webapp_router)
    dp.include_router(user.router)
    dp.include_router(payments.router)
    dp.include_router(admin.router)
    dp.include_router(group_router)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        check_expired, trigger="interval", seconds=30,
        args=[bot], id="check_expired", replace_existing=True,
    )
    scheduler.start()
    logger.info("✅ Планировщик запущен")

    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    logger.info(f"✅ Бот запущен: @{me.username}")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await api_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
