
import asyncio
import logging
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
log = logging.getLogger("vartaua.power")

BASE_DIR = Path(__file__).resolve().parent

CHANNEL = "lvivoblenergo"
TELEGRAM_URL = f"https://t.me/s/{CHANNEL}"
SCHEDULE_URL = "https://dkr.ova.net.ua/api/schedule"

QUEUES = [
    "1.1", "1.2", "2.1", "2.2",
    "3.1", "3.2", "4.1", "4.2",
    "5.1", "5.2", "6.1", "6.2",
]

feed_cache = {
    "items": [],
    "checked_at": None,
    "attempted_at": 0.0,
    "error": None,
}

schedule_cache = {
    "data": None,
    "checked_at": None,
    "attempted_at": 0.0,
    "error": None,
}

feed_lock = asyncio.Lock()
schedule_lock = asyncio.Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class TelegramParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.wrap_depth = 0
        self.text_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()

        if "tgme_widget_message_wrap" in classes:
            self.current = {
                "text": "",
                "date": "",
                "url": "",
            }
            self.wrap_depth = 1
            self.text_depth = 0
            return

        if self.current is None:
            return

        if tag == "div":
            self.wrap_depth += 1

        if "tgme_widget_message_text" in classes:
            self.text_depth = 1
        elif self.text_depth and tag not in (
            "br", "img", "input", "meta"
        ):
            self.text_depth += 1

        if (
            tag == "a"
            and "tgme_widget_message_date" in classes
        ):
            self.current["url"] = attrs.get("href", "")

        if tag == "time":
            self.current["date"] = attrs.get(
                "datetime", ""
            )

        if tag == "br" and self.text_depth:
            self.current["text"] += "\n"

    def handle_data(self, data):
        if self.current and self.text_depth:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if self.current is None:
            return

        if tag == "div":
            self.wrap_depth -= 1

        if self.text_depth and tag not in (
            "br", "img", "input", "meta"
        ):
            self.text_depth -= 1

        if self.wrap_depth <= 0:
            item = self.current
            self.current = None
            self.text_depth = 0

            item["text"] = " ".join(
                item["text"].split()
            )

            if (
                item["text"]
                and item["url"].startswith(
                    f"https://t.me/{CHANNEL}/"
                )
            ):
                self.items.append(item)


async def get_feed():
    async with feed_lock:
        now = time.monotonic()

        if now - feed_cache["attempted_at"] < 120:
            return feed_cache

        feed_cache["attempted_at"] = now

        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    TELEGRAM_URL,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    },
                )
                response.raise_for_status()

            parser = TelegramParser()
            parser.feed(response.text)

            unique = {
                item["url"]: item
                for item in parser.items
            }

            if not unique:
                raise ValueError(
                    "Не вдалося прочитати повідомлення"
                )

            feed_cache["items"] = list(
                reversed(list(unique.values()))
            )[:15]

            feed_cache["checked_at"] = utc_now()
            feed_cache["error"] = None

        except Exception as exc:
            log.warning("Power feed: %s", exc)
            feed_cache["error"] = str(exc)

        return feed_cache


async def get_schedule():
    async with schedule_lock:
        now = time.monotonic()

        if (
            now - schedule_cache["attempted_at"]
            < 300
        ):
            return schedule_cache

        schedule_cache["attempted_at"] = now

        try:
            async with httpx.AsyncClient(
                timeout=15,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    SCHEDULE_URL,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "VartaUA/1.0",
                    },
                )
                response.raise_for_status()
                data = response.json()

            if not isinstance(data, (dict, list)):
                raise ValueError(
                    "Невідомий формат графіків"
                )

            if not data:
                raise ValueError(
                    "Джерело повернуло порожні дані"
                )

            schedule_cache["data"] = data
            schedule_cache["checked_at"] = utc_now()
            schedule_cache["error"] = None

        except Exception as exc:
            log.warning("Power schedule: %s", exc)
            schedule_cache["error"] = str(exc)

        return schedule_cache


@router.get("/power")
async def power_page():
    return FileResponse(
        BASE_DIR / "power.html"
    )


@router.get("/api/power")
async def power_feed():
    cache = await get_feed()

    return {
        "source": TELEGRAM_URL,
        "items": cache["items"],
        "checked_at": cache["checked_at"],
        "error": cache["error"],
    }


@router.get("/api/power/schedule")
async def power_schedule():
    cache = await get_schedule()

    return {
        "source": SCHEDULE_URL,
        "source_type": "third_party",
        "queues": QUEUES,
        "data": cache["data"],
        "checked_at": cache["checked_at"],
        "error": cache["error"],
        "available": (
            cache["data"] is not None
            and cache["error"] is None
        ),
    }
