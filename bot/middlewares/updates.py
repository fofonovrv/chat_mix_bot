from aiogram.types import Update
from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
import logging

logger = logging.getLogger(__name__)

class AllUpdatesMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        logger.debug(f"Incoming update:\n{event.model_dump_json(indent=2)}")
        return await handler(event, data)
