import os
import re
import asyncio
import time
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
from telegram.request import HTTPXRequest

from tgstat import get_post_views, get_post_data
from sheets import add_post, mark_deleted
from scheduler import scheduler, schedule_post_jobs, restore_jobs_on_startup

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

TG_POST_RE = re.compile(r"https://t\.me/([\w\d_]+)/(\d+)")


def parse_tg_url(url: str):
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

    # Берём дату публикации из TGStat
    post_data = await get_post_data(url)
    if post_data and post_data.get("date"):
        pub_date = post_data["date"]
    else:
        pub_date = datetime.now()

    try:
        row_num = add_post(f"@{channel}", url, pub_date)
    except Exception as e:
        await update.message.reply_text(f"Ошибка при записи в таблицу: {e}")
        return

    schedule_post_jobs(url, pub_date, context.bot, chat_id)

    await update.message.reply_text(
        f"Пост добавлен в таблицу (строка {row_num}).\n\n"
        f"Канал: @{channel}\n"
        f"Дата публикации: {pub_date.strftime('%d.%m.%Y')}\n\n"
        f"Что дальше:\n"
        f"• Через 24ч сниму просмотры\n"
        f"• В конце {pub_date.strftime('%B')} сниму просмотры\n"
        f"• Через 30 дней напомню об удалении"
    )


async def deleted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "Не удалось получить просмотры через TGStat.\n"
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
    # Увеличенные таймауты для нестабильных соединений
    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=30,
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deleted", deleted_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    scheduler.start()

    chat_id = os.getenv("CHAT_ID")
    if chat_id:
        restore_jobs_on_startup(app.bot, int(chat_id))

    print("Бот запущен!")

    # Retry loop — если соединение обрывается, перезапускаем
    while True:
        try:
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
        except Exception as e:
            print(f"Бот упал с ошибкой: {e}. Перезапуск через 10 секунд...")
            time.sleep(10)


if __name__ == "__main__":
    main()
