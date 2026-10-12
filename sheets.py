import gspread
from google.oauth2.service_account import Credentials
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

SHEET_ID = os.getenv("SHEET_ID")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Индексы колонок (0-based)
COL_CHANNEL = 0       # A - Канал
COL_URL = 1           # B - Ссылка
COL_DATE = 2          # C - Дата публикации
COL_VIEWS_24H = 3     # D - Views через 24ч
COL_VIEWS_MONTH = 4   # E - Views конец месяца
COL_VIEWS_FINAL = 5   # F - Views финал
COL_STATUS = 6        # G - Статус


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    return sheet


def add_post(channel: str, url: str, pub_date: datetime) -> int:
    """
    Добавляет новую строку с постом.
    Возвращает номер строки (1-based).
    """
    sheet = get_sheet()
    row = [
        channel,
        url,
        pub_date.strftime("%d.%m.%Y"),
        "",   # views 24h
        "",   # views конец месяца
        "",   # views финал
        "Активен",
    ]
    sheet.append_row(row)
    all_rows = sheet.get_all_values()
    return len(all_rows)  # номер последней строки


def update_views(url: str, column: int, views: int):
    """
    Обновляет просмотры в нужной колонке для строки с данным URL.
    column — одна из констант COL_VIEWS_*
    """
    sheet = get_sheet()
    all_rows = sheet.get_all_values()

    for i, row in enumerate(all_rows):
        if len(row) > COL_URL and row[COL_URL] == url:
            row_number = i + 1  # gspread использует 1-based индексы
            col_letter = chr(ord('A') + column)
            sheet.update(f"{col_letter}{row_number}", [[views]])
            return True
    return False


def mark_deleted(url: str, views: int):
    """
    Ставит финальные просмотры и статус 'Удалён'.
    """
    sheet = get_sheet()
    all_rows = sheet.get_all_values()

    for i, row in enumerate(all_rows):
        if len(row) > COL_URL and row[COL_URL] == url:
            row_number = i + 1
            sheet.update(f"F{row_number}", [[views]])
            sheet.update(f"G{row_number}", [["Удалён"]])
            return True
    return False


def get_all_active_posts() -> list[dict]:
    """
    Возвращает все активные посты как список словарей.
    """
    sheet = get_sheet()
    all_rows = sheet.get_all_values()

    posts = []
    for i, row in enumerate(all_rows):
        if i == 0:
            continue  # пропускаем заголовок
        if len(row) >= 7 and row[COL_STATUS] == "Активен":
            posts.append({
                "row": i + 1,
                "channel": row[COL_CHANNEL],
                "url": row[COL_URL],
                "pub_date": row[COL_DATE],
                "views_24h": row[COL_VIEWS_24H],
                "views_month": row[COL_VIEWS_MONTH],
                "views_final": row[COL_VIEWS_FINAL],
                "status": row[COL_STATUS],
            })
    return posts
