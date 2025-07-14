from bot.bot import main
import logging
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    import asyncio
    logger.info('Запускаем бота...')
    asyncio.run(main()) 