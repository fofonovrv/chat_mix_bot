import random
from datetime import datetime, time, timezone
from bot.ai import get_character_reply
from bot.config import GENNADY_PERSONA
from bot.dbmap import get_last_messages

def parse_datetime_args(args: list[str]) -> tuple[datetime, datetime] | None:
    try:
        if len(args) == 0:
            today = datetime.now(timezone.utc).date()
            start = datetime.combine(today, time.min).replace(tzinfo=timezone.utc)
            end = datetime.combine(today, time.max).replace(tzinfo=timezone.utc)
        elif len(args) == 4:
            start = datetime.strptime(f"{args[0]} {args[1]}", "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
            end = datetime.strptime(f"{args[2]} {args[3]}", "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
        else:
            return None
        return start, end
    except Exception:
        return None

def build_history_text(messages):
    history_lines = []
    for m in messages:
        user = m.messages_from_user
        if user is None:
            continue
        dt_str = m.date.strftime("%d-%m-%Y %H:%M")
        username = user.username or "no_username"
        full_name = f"{user.last_name or ''} {user.first_name or ''}".strip()
        history_lines.append(f"{dt_str} {username} {full_name}:\n{m.text.strip()}\n")
    return "\n".join(history_lines)

def get_text_for_message(msg):
    if hasattr(msg, 'text') and msg.text:
        return msg.text
    if hasattr(msg, 'caption') and msg.caption:
        return msg.caption
    return None

async def maybe_bot_reply(msg, *, probability: float = 0.05, recent_limit: int = 15):
    from bot import bot, bot_username
    chat_id = msg.chat.id
    recent_messages = get_last_messages(chat_id, limit=recent_limit)
    if any(m.messages_from_user.username == bot_username for m in recent_messages):
        return
    if random.random() < probability:
        messages = get_last_messages(chat_id, limit=10)
        history_text = build_history_text(messages)
        reply_text = await get_character_reply(f'Придумай сообщение для чата\nКонтекст:\n{history_text}', persona=GENNADY_PERSONA)
        await bot.send_message(chat_id=chat_id, text=reply_text) 