import asyncio
import logging
from aiogram import Bot, types
from aiogram.types import Message, InputFile, Poll, PollAnswer, Update,  MessageReactionUpdated
from aiogram.types.input_file import FSInputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram import Dispatcher, Router, F
from aiogram.filters import Command #, ReactionFilter
from config import TG_TOKEN, ADMIN_LIST, GENNADY_PERSONA, HELP_TEXT
from sqlalchemy.orm import scoped_session, sessionmaker, joinedload
from dbmap import engine, get_user, write_msg_to_db, self_user, admin_user, get_messages_by_chat_and_range, get_last_summary
from dbmap import get_text_for_message, get_statistic, get_last_messages, write_poll_to_db, get_poll_from_db
from dbmap import session, TgUser, get_display_name, get_user_by_tg_id, build_history_text, get_msg_by_tg_msg_id
import json
from ai import get_summary_llm, get_character_reply
from datetime import datetime, time, timedelta, timezone
from middlewares.error_handler import NetworkErrorMiddleware
from middlewares.updates import AllUpdatesMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types.reaction_type_emoji import ReactionTypeEmoji
import random

router = Router(name=__name__)
self_user = None
bot_username = None
bot = None
logger = logging.getLogger(__name__)


async def init_bot_info(bot):
    global self_user, bot_username

    # Получаем информацию о боте от Telegram
    me = await bot.get_me()
    bot_username = me.username.lower()

    # Пытаемся найти бота в БД
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


async def maybe_bot_reply(msg: Message, *, probability: float = 0.05, recent_limit: int = 15):
    """
    Отправляет  ответ, если среди последних `recent_limit` сообщений нет сообщений от бота,
    и с заданной вероятностью `probability`.
    """
    chat_id = msg.chat.id
    recent_messages = get_last_messages(chat_id, limit=recent_limit)
    if any(m.messages_from_user.username == bot_username for m in recent_messages):
        return  # Бот уже недавно писал — не отвечаем

    if random.random() < probability:
        messages = get_last_messages(chat_id, limit=10)
        history_text = build_history_text(messages)
        reply_text = await get_character_reply(f'Придумай сообщение для чата\nКонтекст:\n{history_text}', persona=GENNADY_PERSONA)
        await bot.send_message(chat_id=chat_id, text=reply_text)


@router.message(Command('start'))
async def process_start_command(message: Message):
	await bot.send_message(message.from_user.id, 'Здравствуйте.\n' + HELP_TEXT)


@router.message(Command('help'))
async def process_help_command(message: Message):
	await bot.send_message(message.from_user.id, HELP_TEXT)


def parse_datetime_args(args: list[str]) -> tuple[datetime, datetime] | None:
    try:
        if len(args) == 0:
            today = datetime.now(timezone.utc).date()
            start = datetime.combine(today, time.min).replace(tzinfo=timezone.utc)
            end = datetime.combine(today, time.max).replace(tzinfo=timezone.utc)
        elif len(args) == 4:
            # /summary 01.07.2025 10:00 01.07.2025 15:00
            start = datetime.strptime(f"{args[0]} {args[1]}", "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
            end = datetime.strptime(f"{args[2]} {args[3]}", "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
        else:
            return None
        return start, end
    except Exception as e:
        return None


@router.message(Command("statistic"))
async def cmd_statistic(msg: Message):
    logger.info('Получаем статистику...')
    stat_text = get_statistic()
    await msg.reply(stat_text)


@router.message(Command("summary"))
async def summary_command(msg: Message):
    args = msg.text.strip().split()[1:]
    parsed = parse_datetime_args(args)

    if not parsed:
        await msg.answer("Неверный формат.\nПример: /summary 01.07.2025 10:00 01.07.2025 15:00")
        return

    start, end = parsed
    chat_id = msg.chat.id

    messages = get_messages_by_chat_and_range(chat_id, start, end)

    if not messages:
        await msg.answer("В указанный период сообщений не найдено.")
        return

    history_text = build_history_text(messages)

    await msg.answer("Создаю саммари, подождите...")

    style = "напиши с юмором, подкалывая некоторых участников чата. Не бойся быть дерзким, чтобы было еще смешнее"

    summary = await get_summary_llm(history_text, style)

    for i in range(0, len(summary), 4000):
        await msg.answer(summary[i:i+4000])


@router.message(Command("lastsummary"))
async def last_summary_command(msg: Message):
    chat_id = msg.chat.id
    summary = get_last_summary(chat_id)

    if not summary:
        await msg.answer("Саммари в этом чате ещё не создавались.")
        return

    header = (
        f"Последнее саммари от {summary.created_at.strftime('%d.%m.%Y %H:%M')} "
        f"(модель: {summary.author})\n"
        f"Диапазон: {summary.range_start.strftime('%d.%m.%Y %H:%M')} — {summary.range_end.strftime('%d.%m.%Y %H:%M')}"
    )
    if summary.style:
        header += f"\nСтиль: {summary.style}"

    await msg.answer(header)

    for i in range(0, len(summary.text), 4000):
        await msg.answer(summary.text[i:i+4000])


@router.message(F.poll)
async def handle_poll_message(msg: Message):
    poll = msg.poll
    chat_id = msg.chat.id

    # Сохраняем поля
    question = poll.question
    options = [o.text for o in poll.options]
    is_anonymous = poll.is_anonymous
    allows_multiple_answers = poll.allows_multiple_answers

    # Ищем имя автора
    user = msg.from_user
    db_user = get_user(user)
    prefix = f"Опрос от {get_display_name(db_user)}"

    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except TelegramBadRequest:
        pass


    # Формируем текст опроса
    poll_text = f"Опрос: {question}\nВарианты:\n"
    for opt in poll.options:
        poll_text += f"- {opt.text}\n"

    # Записываем это сообщение в базу от пользователя
    write_msg_to_db(
        text=poll_text.strip(),
        from_user=db_user,
        chat_id=chat_id,
        tg_message_id=msg.message_id
    )

    # Создаём новый опрос с префиксом
    new_poll = await bot.send_poll(
        chat_id=chat_id,
        question=f"{prefix}\n\n{question}",
        options=options,
        is_anonymous=is_anonymous,
        allows_multiple_answers=allows_multiple_answers
    )

    # Сохраняем в базу
    write_poll_to_db(new_poll.poll, chat_id=chat_id)

@router.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer):
    logger.info("Получен ответ на опрос")
    user = get_user_by_tg_id(poll_answer.user.id)
    poll = get_poll_from_db(poll_id=poll_answer.poll_id)

    if not user:
        logger.warning(f"Пользователь не найден в БД: {poll_answer.user}")
        return

    if not poll:
        logger.warning(f"Опрос с poll_id={poll_answer.poll_id} не найден в БД")
        return

    try:
        selected_options = poll_answer.option_ids
        poll_data = json.loads(poll.options)
        question = poll_data.get("question", "<вопрос не найден>")
        options = poll_data.get("options", [])

        for option_index in selected_options:
            try:
                option_text = options[option_index]["text"]
            except IndexError:
                option_text = "<неизвестный вариант>"
            full_text = (
                f"Опрос: {question}\n"
                f"Варианты: \n{'\n -'.join(opt['text'] for opt in options)}\n"
                f"{user} проголосовал за: '{option_text}'"
            )

            write_msg_to_db(
                text=full_text,
                from_user=user,
                chat_id=poll.chat_id or 0,
            )

            logger.info(f"{user} проголосовал за '{option_text}'")

    except Exception as e:
        logger.exception(f"Ошибка при обработке ответа на опрос: {e}")


@router.message_reaction()
async def handle_reaction(event: MessageReactionUpdated):
    chat_id = event.chat.id
    reacting_user = get_user(event.user)  # ваша функция для поиска/добавления пользователя в БД
    tg_message_id = event.message_id

    # Получим сообщение, на которое была реакция
    original_msg = get_msg_by_tg_msg_id(chat_id, tg_message_id)
    if not original_msg:
        logger.warning(f"Оригинальное сообщение {tg_message_id} не найдено в БД.")
        return

    # Преобразуем реакцию в текст, например: 😄
    # event.new_reaction — список объектов типа MessageReaction
    reactions = [
        r.emoji for r in event.new_reaction if str(r.type) == 'emoji'
    ]
    if not reactions:
        logger.warning(f"Реакция {tg_message_id} не содержит текста.")
        return 

    text = f"Реакция: {''.join(reactions)}"

    write_msg_to_db(
        text=text,
        from_user=reacting_user,
        chat_id=chat_id,
        reply_to_tg_msg_id=tg_message_id
    )


@router.message(F.entities, ~F.text.startswith("/"))
async def handle_bot_mention(msg: Message):
    if not msg.entities or not msg.text:
        return
    if not any(
        ent.type == "mention" and f"@{bot_username}" in msg.text.lower()
        for ent in msg.entities
    ):
        return

    text_clean = msg.text.replace(f"@{bot_username}", "").strip()
    if not text_clean:
        await msg.reply("Ну и чего ты хотел, тегнул и молчишь?")
        return

    try:
        thinking_msg = await msg.reply("Дай подумать...")

        messages = get_last_messages(chat_id=msg.chat.id, limit=10)
        history_lines = []
        for m in messages:
            user = m.messages_from_user
            if user is None:
                continue
            dt_str = m.date.strftime("%d-%m-%Y %H:%M")
            username = user.username or "no_username"
            full_name = f"{user.last_name or ''} {user.first_name or ''}".strip()
            history_lines.append(f"{dt_str} {username} {full_name}:\n{m.text.strip()}\n")

        history_text = "\n".join(history_lines)
        reply_text = await get_character_reply(f'{text_clean}\nКонтекст:\n{history_text}', persona=GENNADY_PERSONA)

        await thinking_msg.delete()
        response_msg = await msg.reply(reply_text)

        write_msg_to_db(
            text=reply_text,
            from_user=user,
            chat_id=msg.chat.id,
            tg_message_id=msg.message_id,
            reply_to_tg_msg_id=msg.reply_to_message.message_id if msg.reply_to_message else None
        )
    except Exception as e:
        await msg.reply("Геннадий временно молчит. Скажите, чтобы @iromess проверил.")
        logger.error("handle_bot_mention error:")


@router.message(~F.text.startswith("/"))
async def handle_all_messages(msg: Message):
    user = get_user(msg.from_user)
    text = get_text_for_message(msg)
    if not text:
        return

    write_msg_to_db(
        text=text,
        from_user=user,
        chat_id=msg.chat.id,
        tg_message_id=msg.message_id,
        reply_to_tg_msg_id=msg.reply_to_message.message_id if msg.reply_to_message else None
    )

    # Случайным образом ответить в чат
    # await maybe_bot_reply(msg, probability=0.05, recent_limit=15)


@router.message()
async def catch_all(msg: Message):
    user = get_user(msg.from_user)
    text = get_text_for_message(msg)
    if not text:
        return

    write_msg_to_db(
        text=text,
        from_user=user,
        chat_id=msg.chat.id,
        tg_message_id=msg.message_id,
        reply_to_tg_msg_id=msg.reply_to_message.message_id if msg.reply_to_message else None
    )



async def main() -> None:
    global bot 
    bot = Bot(token=TG_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Обработка middleware
    dp.message.middleware(NetworkErrorMiddleware())
    dp.callback_query.middleware(NetworkErrorMiddleware())
    # dp.message.middleware(AllUpdatesMiddleware())
    # dp.edited_message.middleware(AllUpdatesMiddleware())
    # dp.inline_query.middleware(AllUpdatesMiddleware())
    # dp.chosen_inline_result.middleware(AllUpdatesMiddleware())
    # dp.callback_query.middleware(AllUpdatesMiddleware())
    # dp.poll.middleware(AllUpdatesMiddleware())
    # dp.poll_answer.middleware(AllUpdatesMiddleware())

    await bot.delete_webhook(drop_pending_updates=True)
    await init_bot_info(bot)
    await dp.start_polling(bot)
    

if __name__ == '__main__':
	logger.info('Запускаем бота...')
	asyncio.run(main())