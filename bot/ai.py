import logging
import datetime as dt
from openai import AsyncOpenAI
from bot.config import OPENAI_API_KEY, OPENAI_MODEL, GENNADY_PERSONA
from bot.dbmap import save_summary_to_db

logger = logging.getLogger(__name__)
client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    timeout=30.0,
    #http_client=httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=500, max_connections=100)),
    max_retries=0
)

DEFAULT_PROMPT = (
    "Прочитай диалог ниже и сделай краткое, интересное и содержательное саммари. "
    "Если есть шутки, ирония или важные моменты — выдели их. "
    "Сохрани суть разговора, кто что говорил.\n\n"
)


async def get_summary_llm(
    history_text: str,
    style: str = "",
    chat_id: int = 0,
    start: dt.datetime = None,
    end: dt.datetime = None
) -> str:
    prompt = (
        "Ты — LLM, которая умеет делать саммари из переписок в Telegram. "
        "Собери суть обсуждения из истории сообщений. Не перечисляй всё по пунктам, "
        "а напиши связный текст, как будто ты рассказываешь другу, что обсуждали в чате."
    )

    if style:
        prompt += f"\nСтиль: {style}"

    if GENNADY_PERSONA:
        prompt += f"\nРоль: {GENNADY_PERSONA['description']}"

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": history_text}
    ]

    try:
        logger.info("Отправка запроса к OpenAI (get_summary_llm)")
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.9,
            max_tokens=2000
        )
        summary_text = response.choices[0].message.content.strip()

        save_summary_to_db(
            chat_id=chat_id,
            author=OPENAI_MODEL,
            text=summary_text,
            start=start or dt.datetime.utcnow(),
            end=end or dt.datetime.utcnow(),
            style=style
        )

        return summary_text

    except Exception as e:
        logger.error(f"Ошибка при обращении к OpenAI: {e}")
        return f"Ошибка при обращении к OpenAI: {e}"


async def get_character_reply(text: str, persona: dict = GENNADY_PERSONA) -> str:
    messages = [
        {"role": "system", "content": persona["description"]},
        {"role": "user", "content": text},
    ]

    try:
        logger.info(f'Отправка запроса к OpenAI (get_character_reply)')
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=100,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Ошибка при генерации реплики персонажа: {e}")
        return f"Ошибка: {e}"
