"""Read-only Telegram monitoring of public channel posts for western Ukraine.
Requires a separately authorized Telegram account session; no scraping or fake coordinates.
"""
import asyncio
import logging
import os
import re
from collections import deque
from datetime import datetime, timezone, timedelta

log = logging.getLogger("vartaua.telegram")
CHANNELS = ("kpszsu", "war_monitor_ua")
# Explicitly prioritize Lviv and adjacent oblasts; don't interpret a place name as a target coordinate.
REGIONS = {
 "Львівська": ("львів", "львівщ", "дрогобич", "стрий", "самбір", "яворів", "золочів", "сокаль", "червоноград", "шептицьк", "трускавець", "борислав", "брод", "жовкв", "мостиськ", "городок"),
 "Волинська": ("волин", "луцьк", "ковель", "володимир", "нововолинськ"),
 "Рівненська": ("рівнен", "рівне", "дубно", "сарн", "вараш", "костопіл"),
 "Тернопільська": ("тернопіл", "чортків", "кременець", "бережан"),
 "Івано-Франківська": ("франків", "калуш", "коломи", "долин", "надвірн", "яремче"),
 "Закарпатська": ("закарпат", "ужгород", "мукачев", "хуст", "берегов"),
}
FEED = deque(maxlen=250)
STATE = {"configured": False, "connected": False, "last_check": None, "error": None}
MAX_AGE = timedelta(hours=6)
DANGER_WORDS = ("бпла", "шахед", "дрон", "ракета", "ракет", "крилат", "баліст", "авіац", "каб", "загроз", "тривог", "ппо", "вибух")
def extract_regions(message):
    text = message.casefold()
    return [name for name, terms in REGIONS.items() if any(term in text for term in terms)]
def relevant(message):
    text = message.casefold()
    return bool(extract_regions(message)) and any(word in text for word in DANGER_WORDS)
def recent_items():
    now = datetime.now(timezone.utc)
    return [item for item in FEED if now - datetime.fromisoformat(item["published_at"]) <= MAX_AGE]
async def monitor_telegram():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_SESSION", "").strip()
    if not (api_id and api_hash and session):
        STATE["error"] = "Потрібні TELEGRAM_API_ID, TELEGRAM_API_HASH і TELEGRAM_SESSION"
        return
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(session), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            STATE["error"] = "Telegram session is not authorized"
            await client.disconnect()
            return
        STATE["configured"] = True
        STATE["connected"] = True
        sources = {}
        for channel in CHANNELS:
            try:
                sources[channel] = await client.get_entity(channel)
            except Exception as exc:
                log.warning("Telegram source %s unavailable: %s", channel, exc)
        if not sources:
            STATE["error"] = "Жодне джерело Telegram недоступне"
            await client.disconnect()
            return
        while True:
            try:
                now = datetime.now(timezone.utc)
                existing = {(x["source"], x["message_id"]) for x in FEED}
                for name, entity in sources.items():
                    async for message in client.iter_messages(entity, limit=25):
                        body = (message.raw_text or "").strip()
                        if not body or not message.date or now - message.date > MAX_AGE or not relevant(body):
                            continue
                        key = (name, message.id)
                        if key in existing:
                            continue
                        FEED.appendleft({
                            "source": name, "source_type": "official" if name == "kpszsu" else "monitoring",
                            "message_id": message.id, "url": f"https://t.me/{name}/{message.id}",
                            "published_at": message.date.astimezone(timezone.utc).isoformat(),
                            "regions": extract_regions(body), "text": body[:1800],
                            "position_verified": False, "count_verified": False, "direction_verified": False,
                        })
                        existing.add(key)
                STATE["last_check"] = datetime.now(timezone.utc).isoformat()
                STATE["error"] = None
                STATE["connected"] = True
            except Exception as exc:
                STATE["error"] = type(exc).__name__ + ": " + str(exc)[:150]
                STATE["connected"] = False
                log.warning("Telegram monitoring error: %s", exc)
            await asyncio.sleep(90)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        STATE["error"] = type(exc).__name__ + ": " + str(exc)[:150]
        log.exception("Telegram monitor failed")
