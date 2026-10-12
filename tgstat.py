import httpx
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TGSTAT_TOKEN = os.getenv("TGSTAT_TOKEN")
BASE_URL = "https://api.tgstat.ru"

TG_POST_RE = re.compile(r"https://t\.me/([\w\d_]+)/(\d+)")


async def get_post_data(post_url: str):
    """
    Получает просмотры и дату публикации поста через TGStat API.
    Возвращает словарь {"views": int, "date": datetime} или None если ошибка.
    """
    match = TG_POST_RE.search(post_url)
    if not match:
        print(f"Cannot parse URL: {post_url}")
        return None

    channel = match.group(1)
    post_id = int(match.group(2))

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for offset in [0, 50, 100]:
                response = await client.get(
                    f"{BASE_URL}/channels/posts",
                    params={
                        "token": TGSTAT_TOKEN,
                        "channelId": channel,
                        "limit": 50,
                        "offset": offset,
                    },
                )
                data = response.json()

                if data.get("status") == "ok":
                    items = data.get("response", {}).get("items", [])
                    for item in items:
                        link = item.get("link", "")
                        if link == f"t.me/{channel}/{post_id}":
                            views = item.get("views", None)
                            pub_timestamp = item.get("date", None)
                            pub_date = datetime.fromtimestamp(pub_timestamp) if pub_timestamp else datetime.now()
                            return {"views": views, "date": pub_date}
                else:
                    print(f"TGStat error: {data}")
                    return None

            print(f"Post not found in channel feed: {post_url}")
            return None
    except Exception as e:
        print(f"TGStat request failed: {e}")
        return None


async def get_post_views(post_url: str):
    """
    Получает только просмотры поста.
    """
    data = await get_post_data(post_url)
    if data:
        return data["views"]
    return None
