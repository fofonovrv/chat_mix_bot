import asyncio
import logging
from aiogram import Bot, Dispatcher
from bot.config import TG_TOKEN
from bot.dbmap import session, TgUser
from bot.middlewares.error_handler import NetworkErrorMiddleware
from bot.handlers import router

bot = None
self_user = None
bot_username = None
logger = logging.getLogger(__name__)

async def init_bot_info(bot):
    global self_user, bot_username
    me = await bot.get_me()
    bot_username = me.username.lower()
    self_user = session.query(TgUser).filter(TgUser.tg_id == me.id).scalar()
    if not self_user:
        self_user = TgUser(
            tg_id=me.id,
            username=me.username,
            first_name=me.first_name,
            last_name=me.last_name
        )
        session.add(self_user)
        session.commit()
        logger.info(f"Добавлен бот-пользователь в БД: {self_user}")
    else:
        logger.info(f"Бот-пользователь уже в БД: {self_user}")

async def main() -> None:
    global bot
    bot = Bot(token=TG_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    dp.message.middleware(NetworkErrorMiddleware())
    dp.callback_query.middleware(NetworkErrorMiddleware())
    await bot.delete_webhook(drop_pending_updates=True)
    await init_bot_info(bot)
    await dp.start_polling(bot)

# if __name__ == '__main__':
#     logger.info('Запускаем бота...')
#     asyncio.run(main())