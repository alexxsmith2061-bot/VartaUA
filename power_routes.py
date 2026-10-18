
from fastapi import APIRouter
from fastapi.responses import FileResponse
from datetime import datetime, timezone
from html.parser import HTMLParser
import asyncio
import httpx
import time

router = APIRouter()

CHANNEL = "lvivoblenergo"
SOURCE_URL = f"https://t.me/s/{CHANNEL}"

_cache = {
    "items": [],
    "checked_at": None,
    "last_attempt": 0.0,
    "error": None,
}

_lock = asyncio.Lock()


class TelegramParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.message = None
        self.depth = 0
        self.capture_text = 0
        self.capture_date = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")

        if "tgme_widget_message_wrap" in cls.split():
            self.message = {
                "text": "",
                "date": "",
                "url": "",
            }
            self.depth = 1
            return

        if self.message is None:
            return

        if tag == "div":
            self.depth += 1

        if "tgme_widget_message_text" in cls.split():
            self.capture_text += 1

        if tag == "a" and "tgme_widget_message_date" in cls.split():
            self.capture_date += 1
            self.message["url"] = attrs.get("href", "")

        if tag == "time":
            self.message["date"] = attrs.get("datetime", "")

        if self.capture_text and tag == "br":
            self.message["text"] += "\n"

    def handle_data(self, data):
        if self.message is None:
            return

        if self.capture_text:
            self.message["text"] += data

    def handle_endtag(self, tag):
        if self.message is None:
            return

        if tag == "a" and self.capture_date:
            self.capture_date -= 1

        if tag == "div":
            if self.capture_text:
                self.capture_text -= 1

            self.depth -= 1

            if self.depth <= 0:
                item = self.message
                self.message = None
                self.capture_text = 0
                self.capture_date = 0

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


@router.get("/power")
async def power_page():
    return FileResponse("power.html")


@router.get("/api/power")
async def power_feed():
    async with _lock:
        now = time.monotonic()

        if now - _cache["last_attempt"] >= 120:
            _cache["last_attempt"] = now

            try:
                async with httpx.AsyncClient(
                    timeout=15,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 VartaUA/1.0"
                    },
                ) as client:
                    response = await client.get(SOURCE_URL)
                    response.raise_for_status()

                parser = TelegramParser()
                parser.feed(response.text)

                if not parser.items:
                    raise ValueError(
                        "Не вдалося прочитати публічні дописи"
                    )

                # Нові повідомлення першими.
                unique = {}
                for item in parser.items:
                    unique[item["url"]] = item

                _cache["items"] = list(
                    reversed(list(unique.values()))
                )[:15]

                _cache["checked_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                _cache["error"] = None

            except Exception as exc:
                _cache["error"] = str(exc)

        return {
            "source": SOURCE_URL,
            "items": _cache["items"],
            "checked_at": _cache["checked_at"],
            "error": _cache["error"],
        }
