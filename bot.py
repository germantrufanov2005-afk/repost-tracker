import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from tgstat import get_post_views
from sheets import add_post, mark_deleted
from scheduler import scheduler, schedule_post_jobs, restore_jobs_on_startup

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Регулярка для парсинга ссылок вида https://t.me/channel/123
TG_POST_RE = re.compile(r"https://t\.me/([\w\d_]+)/(\d+)")


def parse_tg_url(url: str):
    """
    Парсит ссылку на пост.
    Возвращает (channel, post_id) или None если не совпало.
    """
    match = TG_POST_RE.search(url)
    if match:
        return match.group(1), int(match.group(2))
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"Привет! Я бот для сбора статистики репостов.\n\n"
        f"Отправь мне ссылку на пост в формате:\n"
        f"https://t.me/channel/123\n\n"
        f"Я занесу его в таблицу и буду следить за просмотрами.\n\n"
        f"Твой chat_id: {chat_id}\n"
        f"Сохрани его — он нужен для настройки уведомлений."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    parsed = parse_tg_url(text)
    if not parsed:
        await update.message.reply_text(
            "Не могу распознать ссылку. Отправь в формате:\nhttps://t.me/channel/123"
        )
        return

    channel, post_id = parsed
    url = f"https://t.me/{channel}/{post_id}"

    await update.message.reply_text(f"Обрабатываю пост из @{channel}...")

    pub_date = datetime.now()

    # Заносим в таблицу
    try:
        row_num = add_post(f"@{channel}", url, pub_date)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при записи в таблицу: {e}")
        return

    # Ставим задачи по расписанию
    schedule_post_jobs(url, pub_date, context.bot, chat_id)

    await update.message.reply_text(
        f"Пост добавлен в таблицу (строка {row_num}).\n\n"
        f"Канал: @{channel}\n"
        f"Дата: {pub_date.strftime('%d.%m.%Y')}\n\n"
        f"Что дальше:\n"
        f"• Через 24ч сниму просмотры\n"
        f"• В конце {pub_date.strftime('%B')} сниму просмотры\n"
        f"• Через 30 дней напомню об удалении"
    )


async def deleted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда: /deleted https://t.me/channel/123
    Фиксирует финальные просмотры и закрывает строку.
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "Укажи ссылку на пост:\n/deleted https://t.me/channel/123"
        )
        return

    url = args[0].strip()
    parsed = parse_tg_url(url)
    if not parsed:
        await update.message.reply_text(
            "Не могу распознать ссылку. Формат:\n/deleted https://t.me/channel/123"
        )
        return

    await update.message.reply_text("Снимаю финальные просмотры...")

    views = await get_post_views(url)
    if views is None:
        await update.message.reply_text(
            "Не удалось получить просмотры через TGStat. "
            "Возможно пост уже удалён и данные недоступны.\n"
            "Введи просмотры вручную в таблицу."
        )
        return

    success = mark_deleted(url, views)
    if success:
        await update.message.reply_text(
            f"Готово! Финальные просмотры зафиксированы.\n\n"
            f"Пост: {url}\n"
            f"Views: {views:,}\n"
            f"Статус: Удалён"
        )
    else:
        await update.message.reply_text(
            f"Не нашёл этот пост в таблице. Проверь ссылку."
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда: /stats https://t.me/channel/123
    Показывает текущие просмотры прямо сейчас.
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "Укажи ссылку:\n/stats https://t.me/channel/123"
        )
        return

    url = args[0].strip()
    views = await get_post_views(url)

    if views is not None:
        await update.message.reply_text(
            f"Текущие просмотры:\n{url}\n👁 {views:,}"
        )
    else:
        await update.message.reply_text("Не удалось получить данные от TGStat.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deleted", deleted_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    # Запускаем планировщик
    scheduler.start()

    # Восстанавливаем задачи из таблицы при старте
    # chat_id берём из переменной окружения (узнаешь после первого /start)
    chat_id = os.getenv("CHAT_ID")
    if chat_id:
        restore_jobs_on_startup(app.bot, int(chat_id))

    print("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
