"""Lviv power schedules. Source: OE_OUTAGE_DATA, not a live meter reading."""
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
BASE = Path(__file__).resolve().parent
KYIV = ZoneInfo("Europe/Kyiv")
SOURCE = "https://github.com/yaroslav2901/OE_OUTAGE_DATA"
DATA_URL = "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Lvivoblenerho.json"
QUEUES = [f"{a}.{b}" for a in range(1, 7) for b in (1, 2)]
STATES = {"yes", "no", "maybe", "first", "second"}
CACHE_SECONDS = 300
_cache = {"checked": 0.0, "data": None, "error": None, "fetched_at": None}
_lock = asyncio.Lock()


def parse_source(payload):
    if not isinstance(payload, dict) or payload.get("regionId") != "Lviv":
        raise ValueError("Неправильний регіон або формат джерела")
    fact = payload.get("fact")
    days = fact.get("data") if isinstance(fact, dict) else None
    if not isinstance(days, dict) or not days:
        raise ValueError("У джерелі немає добових графіків")
    parsed = {}
    for timestamp, queues in days.items():
        try:
            day = datetime.fromtimestamp(int(timestamp), KYIV).date().isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            continue
        if not isinstance(queues, dict):
            continue
        result = {}
        for queue in QUEUES:
            hours = queues.get("GPV" + queue)
            if not isinstance(hours, dict):
                continue
            slots = [hours.get(str(i)) for i in range(1, 25)]
            if len(slots) == 24 and all(s in STATES for s in slots):
                result[queue] = slots
        if result:
            parsed[day] = result
    if not parsed:
        raise ValueError("Не знайдено повних перевірених графіків")
    updated = payload.get("lastUpdated")
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("No timezone")
        updated = dt.astimezone(timezone.utc).isoformat()
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Невідома дата оновлення джерела")
    return {"days": parsed, "source_updated": updated, "source_label": fact.get("update")}


async def load_data():
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["checked"] < CACHE_SECONDS:
        return
    if _cache["data"] is None and now - _cache["checked"] < 30:
        return
    async with _lock:
        now = time.monotonic()
        if now - _cache["checked"] < (CACHE_SECONDS if _cache["data"] else 30):
            return
        _cache["checked"] = now
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(DATA_URL, headers={"User-Agent": "VartaUA/1.0", "Accept": "application/json"})
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError("Завеликий файл джерела")
                parsed = parse_source(response.json())
            _cache["data"] = parsed
            _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
            _cache["error"] = None
        except (httpx.HTTPError, ValueError) as exc:
            _cache["error"] = str(exc)


@router.get("/power")
async def power_page():
    return FileResponse(BASE / "power.html")


@router.get("/api/power/schedule")
async def schedule():
    await load_data()
    data = _cache["data"]
    now = datetime.now(timezone.utc)
    today = now.astimezone(KYIV).date().isoformat()
    if not data:
        return {"available": False, "today": today, "days": {}, "queues": QUEUES,
                "error": _cache["error"] or "Джерело недоступне", "source": SOURCE,
                "source_updated": None, "stale": True}
    updated = datetime.fromisoformat(data["source_updated"])
    age = (now - updated).total_seconds()
    # Outdated schedules must never be represented as today's confirmed schedule.
    stale = age < -600 or age > 36 * 3600
    return {"available": bool(data["days"].get(today)) and not stale,
            "today": today, "days": data["days"] if not stale else {},
            "queues": QUEUES, "source": SOURCE,
            "source_updated": data["source_updated"],
            "source_label": data["source_label"], "fetched_at": _cache["fetched_at"],
            "stale": stale, "error": _cache["error"],
            "note": "Плановий графік; аварійні відключення можуть відрізнятися."}
