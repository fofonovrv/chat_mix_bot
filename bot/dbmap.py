import os
import re
import datetime as dt
from bot.config import DB_STRING
from sqlalchemy import create_engine, Column, Integer, Boolean, String, String, DateTime, ForeignKey, Text, desc, JSON
from sqlalchemy.orm import scoped_session, declarative_base, sessionmaker, relationship, Mapper, joinedload
from sqlalchemy.orm.exc import DetachedInstanceError
from aiogram.types import Message, Poll
from aiogram.types.user import User as TelegramUser
from typing import Optional
import logging
import json
logger = logging.getLogger(__name__)

Base = declarative_base()
engine = create_engine(DB_STRING)
session = scoped_session(sessionmaker(bind=engine))

Base.query = session.query_property()


class TgUser(Base):
	__tablename__ = 'users'
	__tableargs__ = {
		'comment': 'Пользователи'
	}
	id = Column(Integer,nullable=False,unique=True,primary_key=True,autoincrement=True)
	tg_id = Column(Integer, comment='ID TG')
	username = Column(String(128), comment='username')
	first_name = Column(String(128), comment='Имя')
	last_name = Column(String(128), comment='Фамилия')
	messages_from = relationship("TgMessage", backref="messages_from_user", lazy="dynamic", foreign_keys='[TgMessage.from_user]')
	def __repr__(self):
		return f'{self.username} ({self.first_name} {self.last_name})'

class TgMessage(Base):
    __tablename__ = 'messages'
    __table_args__ = {'comment': 'Сообщения Telegram'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    from_user = Column(Integer, ForeignKey('users.id'), comment='Отправитель')
    chat_id = Column(Integer, comment='ID чата')
    text = Column(Text, comment='Текст сообщения')
    date = Column(DateTime, comment='Время и дата отправки')

    # Telegram message_id (нужен для reply-to сопоставления)
    tg_message_id = Column(Integer, comment='ID сообщения в Telegram-чате')

    # Ответ на сообщение (внутри базы)
    reply_to_message_id = Column(Integer, ForeignKey('messages.id'), nullable=True, comment="Ответ на сообщение")
    reply_to_message = relationship("TgMessage", remote_side=[id], backref="replies")

    def __repr__(self):
        return f'{self.date}: from {self.from_user}'

class TgSummary(Base):
	__tablename__ = 'summaries'
	__tableargs__ = {
		'comment': 'История сгенерированных саммари'
	}

	id = Column(Integer, primary_key=True, autoincrement=True)
	chat_id = Column(Integer, comment='ID чата')
	author = Column(String(128), comment='LLM или человек, сгенерировавший саммари')
	text = Column(Text, comment='Сгенерированный текст')
	created_at = Column(DateTime, default=dt.datetime.utcnow, comment='Время генерации')
	range_start = Column(DateTime, comment='Начало диапазона')
	range_end = Column(DateTime, comment='Конец диапазона')
	style = Column(Text, nullable=True, comment='Стиль, заданный пользователем')

class TgPoll(Base):
    __tablename__ = "tg_polls"
    id = Column(Integer, primary_key=True)
    poll_id = Column(String, unique=True, nullable=False)
    chat_id = Column(Integer, nullable=True)
    question = Column(String, nullable=False)
    options = Column(JSON, nullable=False)  # Сохраняем список текстов

# Создаем таблицы
#======================================

Base.metadata.create_all(bind=engine)
self_user = session.query(TgUser).filter(TgUser.tg_id==0).scalar()
admin_user = session.query(TgUser).filter(TgUser.id==1).scalar()
if not self_user:
	self_user = TgUser(tg_id=0, username='Bot', first_name='', last_name='')
session.add(self_user)
session.commit()

#======================================

def get_user(telegram_user: TelegramUser) -> TgUser:
    if telegram_user is None:
        raise ValueError("telegram_user is None")

    tg_id = telegram_user.id
    first_name = telegram_user.first_name
    last_name = telegram_user.last_name
    username = telegram_user.username

    user = session.query(TgUser).filter(TgUser.tg_id == tg_id).scalar()

    if not user:
        logger.info(f'Пользователь {username} ({first_name} {last_name}) не найден в БД')
        user = TgUser(
            tg_id=tg_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        session.add(user)
        session.commit()
        logger.info(f'Создан пользователь: {user}')

    return user


def write_msg_to_db(
    *,
    text: str,
    from_user: TgUser,
    chat_id: int,
    tg_message_id: Optional[int] = None,
    reply_to_tg_msg_id: Optional[int] = None
):
    try:
        # Найдём базовое сообщение, если текущее — это ответ
        reply_to_msg = None
        if reply_to_tg_msg_id:
            reply_to_msg = session.query(TgMessage).filter_by(
                chat_id=chat_id,
                tg_message_id=reply_to_tg_msg_id
            ).first()

        message = TgMessage(
            from_user=from_user.id,
            chat_id=chat_id,
            text=text,
            date=dt.datetime.now(),
            tg_message_id=tg_message_id,
            reply_to_message_id=reply_to_msg.id if reply_to_msg else None
        )
        session.add(message)
        session.commit()
        return message
    except Exception as e:
        logger.exception(f"[DB] Ошибка при сохранении сообщения: {e}")
        session.rollback()


def get_messages_by_chat_and_range(chat_id: int, start: dt.datetime, end: dt.datetime) -> list[TgMessage]:
	"""
	Возвращает список сообщений из указанного чата в диапазоне времени [start, end).
	"""
	messages = (
		session.query(TgMessage)
		.options(joinedload(TgMessage.messages_from_user))
		.filter(
			TgMessage.chat_id == chat_id,
			TgMessage.date >= start,
			TgMessage.date < end
		)
		.order_by(TgMessage.date)
		.all()
	)
	return messages


def get_last_messages(chat_id: int, limit: int = 10) -> list[TgMessage]:
    """
    Возвращает последние `limit` сообщений из указанного чата по дате (от старых к новым).
    """
    messages = (
        session.query(TgMessage)
        .options(joinedload(TgMessage.messages_from_user))
        .filter(TgMessage.chat_id == chat_id)
        .order_by(desc(TgMessage.date))
        .limit(limit)
        .all()
    )
    return list(reversed(messages))  # чтобы были в хронологическом порядке


def get_text_for_message(msg: Message) -> str:
    """
    Возвращает текстовое представление сообщения: либо текст, либо
    отметку типа вложения с подписью.
    """
    if msg.text:
        return msg.text

    content_type_labels = {
        "photo": "*фото*",
        "video": "*видео*",
        "audio": "*аудио*",
        "voice": "*голосовое*",
        "document": "*документ*",
        "sticker": "*стикер*",
        "animation": "*GIF*",
        "contact": "*контакт*",
        "location": "*локация*",
        "venue": "*место*",
        "poll": "*опрос*"
    }

    label = content_type_labels.get(msg.content_type, "")
    caption = msg.caption or ""

    return f"{label} {caption}".strip()


def save_summary_to_db(
    chat_id: int,
    author: str,
    text: str,
    start: dt.datetime,
    end: dt.datetime,
    style: str = None
):
    summary = TgSummary(
        chat_id=chat_id,
        author=author,
        text=text,
        range_start=start,
        range_end=end,
        style=style
    )
    session.add(summary)
    session.commit()


def get_last_summary(chat_id: int) -> TgSummary | None:
    return session.query(TgSummary)\
        .filter(TgSummary.chat_id == chat_id)\
        .order_by(TgSummary.created_at.desc())\
        .first()


def get_statistic() -> str:
    from sqlalchemy import func
    logger.info('Делаем запросы статистики к бд...')
    count_users = session.query(func.count(TgUser.id)).scalar()
    count_messages = session.query(func.count(TgMessage.id)).scalar()
    count_summaries = session.query(func.count(TgSummary.id)).scalar()

    return (
        f"📊 Статистика:\n"
        f"👤 Пользователей: {count_users}\n"
        f"💬 Сообщений: {count_messages}\n"
        f"🧠 Саммари: {count_summaries}"
    )


def write_poll_to_db(poll: Poll, chat_id: int):
    data = poll.model_dump()
    data["options"] = [opt.model_dump() for opt in poll.options]

    poll_entry = TgPoll(
        poll_id=poll.id,
        question=poll.question,
        options=json.dumps(data, ensure_ascii=False),  # читаемо
        chat_id=chat_id
    )
    session.add(poll_entry)
    session.commit()


def get_poll_from_db(poll_id: str) -> TgPoll | None:
    return session.query(TgPoll).filter_by(poll_id=poll_id).first()


def get_display_name(user: TgUser) -> str:
    return user.first_name or user.username or "пользователя"


def get_user_by_tg_id(tg_id: int) -> Optional[TgUser]:
    return session.query(TgUser).filter(TgUser.tg_id == tg_id).one_or_none()


def build_history_text(messages: list[TgMessage]) -> str:
    lines = []
    for m in messages:
        user = m.messages_from_user
        dt_str = m.date.strftime("%d-%m-%Y %H:%M")
        username = user.username or "no_username"
        full_name = f"{user.last_name or ''} {user.first_name or ''}".strip()
        line = f"{dt_str} {username} {full_name}:\n"

        # Проверим, является ли сообщение ответом
        if m.reply_to_message:
            try:
                original_text = m.reply_to_message.text.strip()
                short_original = (original_text[:300] + "...") if len(original_text) > 300 else original_text
                line += f"*это ответ на это сообщение:* '{short_original}':\n"
            except DetachedInstanceError:
                line += "*это ответ на сообщение, которое не удалось загрузить*\n"

        line += f"{m.text.strip()}\n"
        lines.append(line)
    return "\n".join(lines)


def get_msg_by_tg_msg_id(chat_id: int, tg_message_id: int) -> Optional[TgMessage]:
    """
    Возвращает сообщение из базы данных по chat_id и Telegram message_id.
    """
    try:
        return (
            session.query(TgMessage)
            .filter_by(chat_id=chat_id, tg_message_id=tg_message_id)
            .first()
        )
    except Exception as e:
        logger.exception(f"[DB] Ошибка при поиске сообщения по tg_message_id={tg_message_id}: {e}")
        return None