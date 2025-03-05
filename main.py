from telegram.ext import Updater, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from utils import send_to_moderation, handle_approval, fetch_recent_memes, is_popular, select_random_channel
from config import BOT_TOKEN, TARGET_CHANNEL_ID, SOURCE_CHANNEL_IDS

# Список для хранения опубликованных ID мемов
published_memes = set()

def handle_message(update: Update, context: CallbackContext):
    """Обработчик входящих сообщений."""
    message = update.effective_message
    channel_id = update.effective_chat.id

    # Проверяем, содержит ли сообщение фото или GIF
    if not (message.photo or message.animation):
        return

    # Получаем уникальный ID сообщения
    message_id = message.message_id

    # Проверяем, не было ли это сообщение уже опубликовано
    if message_id in published_memes:
        return

    # Отправляем мем на модерацию
    send_to_moderation(message, context)

    # Добавляем ID сообщения в список опубликованных
    published_memes.add(message_id)

def post_memes(context: CallbackContext):
    """Функция для публикации мемов."""
    # Шаг 1: Выбираем случайный канал
    selected_channel = select_random_channel()
    if not selected_channel:
        logger.warning("Нет доступных каналов для выбора.")
        return

    # Шаг 2: Получаем последние 10 мемов из канала
    memes = fetch_recent_memes(context.bot, selected_channel, limit=10)
    if not memes:
        logger.info(f"Нет новых мемов в канале {selected_channel}.")
        return

    # Шаг 3: Фильтруем популярные мемы
    popular_memes = [m for m in memes if is_popular(m, selected_channel)]
    if not popular_memes:
        logger.info(f"Нет популярных мемов в канале {selected_channel}.")
        return

    # Шаг 4: Отправляем мемы на модерацию
    for meme in popular_memes:
        if meme.message_id not in published_memes:
            send_to_moderation(meme, context)
            published_memes.add(meme.message_id)

def main():
    """Основная функция для запуска бота."""
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher
    job_queue = updater.job_queue

    # Регистрируем обработчики для всех сообщений из исходных каналов
    for source_channel in SOURCE_CHANNEL_IDS:
        dispatcher.add_handler(MessageHandler(Filters.chat(source_channel) & (Filters.photo | Filters.animation), handle_message))

    # Регистрируем обработчик для кнопки "Одобрить"
    dispatcher.add_handler(CallbackQueryHandler(handle_approval, pattern=r"^approve_\d+$"))

    # Запускаем задачу для публикации мемов каждые 30 минут
    job_queue.run_repeating(post_memes, interval=30 * 60, first=10)

    # Запускаем бота
    updater.start_polling()
    print("Бот запущен!")
    updater.idle()

if __name__ == '__main__':
    main()