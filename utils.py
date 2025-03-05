import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from datetime import datetime, timedelta
from random import choice
from config import MIN_ENGAGEMENT_PERCENTAGE, CHANNEL_COOLDOWN_HOURS

# Настройки логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Словарь для отслеживания времени последнего использования каждого канала
channel_usage = {}

# Список для хранения мемов на модерации
memes_for_moderation = {}

def get_channel_subscribers(bot, chat_id):
    """Получает количество подписчиков канала."""
    try:
        return bot.get_chat_members_count(chat_id)
    except Exception as e:
        logger.error(f"Ошибка при получении количества подписчиков: {e}")
        return 1  # Если не удалось получить, используем значение 1 для избежания деления на ноль

def is_popular(message, channel_id):
    """
    Проверяет, является ли сообщение популярным в рамках канала.
    
    :param message: Объект сообщения
    :param channel_id: ID канала
    :return: True, если мем популярен, иначе False
    """
    subscribers = get_channel_subscribers(message.bot, channel_id)
    if subscribers == 0:
        return False  # Пропускаем каналы без подписчиков

    likes = getattr(message, 'like_count', 0)
    comments = getattr(message, 'comment_count', 0)
    engagement = (likes + comments) / subscribers * 100

    return engagement >= MIN_ENGAGEMENT_PERCENTAGE

def select_random_channel():
    """Выбирает случайный канал, учитывая cooldown."""
    current_time = datetime.now()
    available_channels = []

    for channel in config.SOURCE_CHANNEL_IDS:
        last_used = channel_usage.get(channel, None)
        if not last_used or (current_time - last_used) > timedelta(hours=CHANNEL_COOLDOWN_HOURS):
            available_channels.append(channel)

    if not available_channels:
        logger.warning("Все каналы находятся в cooldown. Ждем...")
        return None

    selected_channel = choice(available_channels)
    channel_usage[selected_channel] = current_time
    return selected_channel

def fetch_recent_memes(bot, channel_id, limit=10):
    """Получает последние N мемов из указанного канала."""
    try:
        messages = bot.get_chat_history(chat_id=channel_id, limit=limit)
        return [msg for msg in messages if msg.photo or msg.animation]
    except TelegramError as e:
        logger.error(f"Ошибка при получении сообщений из канала {channel_id}: {e}")
        return []

def send_to_moderation(message, context):
    """Отправляет мем на модерацию."""
    if message.photo:
        photo_id = message.photo[-1].file_id
        caption = message.caption or ""
    elif message.animation:
        photo_id = message.animation.file_id
        caption = message.caption or ""

    # Создаем кнопку "Одобрить"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Одобрить", callback_data=f"approve_{message.message_id}")]])

    # Отправляем мем в чат модерации
    sent_message = context.bot.send_photo(
        chat_id=config.MODERATION_CHAT_ID,
        photo=photo_id,
        caption=f"{caption}\n\nИсточник: {message.link}",
        reply_markup=keyboard
    )

    # Сохраняем информацию о меме для дальнейшей обработки
    memes_for_moderation[sent_message.message_id] = {
        "original_message": message,
        "moderation_message_id": sent_message.message_id
    }

def handle_approval(update: Update, context: CallbackContext):
    """Обрабатывает одобрение мема модератором."""
    query = update.callback_query
    query.answer()

    # Получаем ID сообщения из callback_data
    _, meme_id = query.data.split("_")
    meme_id = int(meme_id)

    # Ищем мем в списке на модерации
    if meme_id in memes_for_moderation:
        original_message = memes_for_moderation[meme_id]["original_message"]

        # Пересылаем мем в целевой канал
        try:
            if original_message.photo:
                context.bot.send_photo(
                    chat_id=config.TARGET_CHANNEL_ID,
                    photo=original_message.photo[-1].file_id,
                    caption=original_message.caption
                )
            elif original_message.animation:
                context.bot.send_animation(
                    chat_id=config.TARGET_CHANNEL_ID,
                    animation=original_message.animation.file_id,
                    caption=original_message.caption
                )
            logger.info(f"Мем с ID {meme_id} успешно опубликован.")
        except TelegramError as e:
            logger.error(f"Ошибка при публикации мема: {e}")

        # Удаляем сообщение из списка на модерации
        del memes_for_moderation[meme_id]

        # Уведомляем модератора об успешной публикации
        query.edit_message_reply_markup(reply_markup=None)
        query.edit_message_caption(caption="Мем одобрен и опубликован!")
    else:
        logger.warning(f"Мем с ID {meme_id} не найден.")

def forward_meme(message, target_channel_id):
    """Пересылает мем в целевой канал."""
    try:
        if message.photo:
            message.bot.send_photo(chat_id=target_channel_id, photo=message.photo[-1].file_id, caption=message.caption)
        elif message.animation:
            message.bot.send_animation(chat_id=target_channel_id, animation=message.animation.file_id, caption=message.caption)
    except TelegramError as e:
        logger.error(f"Ошибка при отправке мема: {e}")