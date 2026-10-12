import asyncio
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv

from tgstat import get_post_views
from sheets import update_views, get_all_active_posts, COL_VIEWS_24H, COL_VIEWS_MONTH, COL_VIEWS_FINAL

load_dotenv()

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


def get_last_day_of_month(dt: datetime) -> datetime:
    """Возвращает последний день месяца для даты dt."""
    if dt.month == 12:
        last_day = dt.replace(day=31)
    else:
        last_day = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return last_day.replace(hour=20, minute=0, second=0)


async def collect_views_24h(url: str, bot, chat_id: int):
    """Снимает просмотры через 24ч после публикации."""
    views = await get_post_views(url)
    if views is not None:
        update_views(url, COL_VIEWS_24H, views)
        await bot.send_message(
            chat_id=chat_id,
            text=f"📊 Views через 24ч для {url}\n👁 {views:,}"
        )


async def collect_views_end_of_month(url: str, bot, chat_id: int):
    """Снимает просмотры в конце месяца публикации."""
    views = await get_post_views(url)
    if views is not None:
        update_views(url, COL_VIEWS_MONTH, views)
        await bot.send_message(
            chat_id=chat_id,
            text=f"📊 Views на конец месяца для {url}\n👁 {views:,}"
        )


async def collect_views_30d_and_remind(url: str, bot, chat_id: int):
    """Через 30 дней — снимает финальные просмотры и напоминает об удалении."""
    views = await get_post_views(url)
    if views is not None:
        update_views(url, COL_VIEWS_FINAL, views)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"📊 Views через 30 дней для {url}\n"
                f"👁 {views:,}\n\n"
                f"⏰ Пора удалять пост!\n"
                f"Когда удалишь — напиши:\n"
                f"/deleted {url}"
            )
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏰ Пора удалять пост!\n\n"
                f"🔗 {url}\n\n"
                f"Не удалось снять просмотры автоматически.\n"
                f"Когда удалишь — напиши:\n"
                f"/deleted {url}"
            )
        )


def schedule_post_jobs(url: str, pub_date: datetime, bot, chat_id: int):
    """
    Ставит три задачи для нового поста:
    1. Через 24ч — снять просмотры
    2. В последний день месяца публикации в 20:00 — снять просмотры
    3. Через 30 дней — снять финальные просмотры + напомнить об удалении
    """
    now = datetime.now()

    # Задача 1: через 24ч
    time_24h = pub_date + timedelta(hours=24)
    if time_24h > now:
        scheduler.add_job(
            collect_views_24h,
            trigger=DateTrigger(run_date=time_24h),
            args=[url, bot, chat_id],
            id=f"24h_{url}",
            replace_existing=True,
        )

    # Задача 2: последний день месяца
    end_of_month = get_last_day_of_month(pub_date)
    if end_of_month > now:
        scheduler.add_job(
            collect_views_end_of_month,
            trigger=DateTrigger(run_date=end_of_month),
            args=[url, bot, chat_id],
            id=f"month_{url}",
            replace_existing=True,
        )

    # Задача 3: через 30 дней — просмотры + напоминание
    time_30d = pub_date + timedelta(days=30)
    if time_30d > now:
        scheduler.add_job(
            collect_views_30d_and_remind,
            trigger=DateTrigger(run_date=time_30d),
            args=[url, bot, chat_id],
            id=f"30d_{url}",
            replace_existing=True,
        )


def restore_jobs_on_startup(bot, chat_id: int):
    """
    При запуске бота восстанавливает задачи для всех активных постов
    у которых ещё не истекли дедлайны.
    """
    posts = get_all_active_posts()
    now = datetime.now()

    for post in posts:
        try:
            pub_date = datetime.strptime(post["pub_date"], "%d.%m.%Y")
            url = post["url"]

            # 24ч
            if not post["views_24h"]:
                time_24h = pub_date + timedelta(hours=24)
                if time_24h > now:
                    scheduler.add_job(
                        collect_views_24h,
                        trigger=DateTrigger(run_date=time_24h),
                        args=[url, bot, chat_id],
                        id=f"24h_{url}",
                        replace_existing=True,
                    )

            # конец месяца
            if not post["views_month"]:
                end_of_month = get_last_day_of_month(pub_date)
                if end_of_month > now:
                    scheduler.add_job(
                        collect_views_end_of_month,
                        trigger=DateTrigger(run_date=end_of_month),
                        args=[url, bot, chat_id],
                        id=f"month_{url}",
                        replace_existing=True,
                    )

            # 30 дней — просмотры + напоминание
            if not post["views_final"]:
                time_30d = pub_date + timedelta(days=30)
                if time_30d > now:
                    scheduler.add_job(
                        collect_views_30d_and_remind,
                        trigger=DateTrigger(run_date=time_30d),
                        args=[url, bot, chat_id],
                        id=f"30d_{url}",
                        replace_existing=True,
                    )
        except Exception as e:
            print(f"Failed to restore job for {post['url']}: {e}")
