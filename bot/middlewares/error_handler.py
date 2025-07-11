import logging
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramNetworkError
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)

class NetworkErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramNetworkError as e:
            logger.warning(f"Сетевая ошибка Telegram API: {e}")
            # можно тут сделать retry или отправку в очередь
            return None
