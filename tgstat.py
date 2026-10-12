import httpx
import os
import re
from dotenv import load_dotenv

load_dotenv()

TGSTAT_TOKEN = os.getenv("TGSTAT_TOKEN")
BASE_URL = "https://api.tgstat.ru"

TG_POST_RE = re.compile(r"https://t\.me/([\w\d_]+)/(\d+)")


async def get_post_views(post_url: str):
    """
    Получает количество просмотров поста через TGStat API.
    post_url — ссылка вида https://t.me/channel/123
    Возвращает число просмотров или None если ошибка.
    """
    match = TG_POST_RE.search(post_url)
    if not match:
        print(f"Cannot parse URL: {post_url}")
        return None

    channel = match.group(1)
    post_id = int(match.group(2))

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Получаем последние посты канала и ищем нужный по ID
            response = await client.get(
                f"{BASE_URL}/channels/posts",
                params={
                    "token": TGSTAT_TOKEN,
                    "channelId": channel,
                    "limit": 50,
                },
            )
            data = response.json()

            if data.get("status") == "ok":
                items = data.get("response", {}).get("items", [])
                for item in items:
                    link = item.get("link", "")
                    if link == f"t.me/{channel}/{post_id}":
                        return item.get("views", None)

                # Если не нашли в последних 50 — пробуем постатейный метод
                response2 = await client.get(
                    f"{BASE_URL}/channels/posts",
                    params={
                        "token": TGSTAT_TOKEN,
                        "channelId": channel,
                        "limit": 50,
                        "offset": 50,
                    },
                )
                data2 = response2.json()
                if data2.get("status") == "ok":
                    items2 = data2.get("response", {}).get("items", [])
                    for item in items2:
                        link = item.get("link", "")
                        if link == f"t.me/{channel}/{post_id}":
                            return item.get("views", None)

                print(f"Post not found in channel feed: {post_url}")
                return None
            else:
                print(f"TGStat error: {data}")
                return None
    except Exception as e:
        print(f"TGStat request failed: {e}")
        return None
