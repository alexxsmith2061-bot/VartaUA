"""Lviv power schedules. Source: OE_OUTAGE_DATA, not a live meter reading."""
import asyncio
import re
import html
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
OFFICIAL_URL = "https://api.loe.lviv.ua/api/menus?page=1&type=photo-grafic"
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



def parse_official(payload):
    """Parse official photo-grafic text, rejecting ambiguous and undated records."""
    if isinstance(payload, list):
        menus = payload
    elif isinstance(payload, dict):
        menus = payload.get("hydra:member", [])
    else:
        raise ValueError("Неправильна відповідь офіційного API")
    if not isinstance(menus, list):
        raise ValueError("Неправильний список офіційних графіків")
    days = {}
    updated_by_day = {}
    for menu in menus:
        if not isinstance(menu, dict):
            continue
        for item in menu.get("menuItems", []):
            if not isinstance(item, dict):
                continue
            raw = item.get("rawHtml", "")
            if not isinstance(raw, str) or len(raw) > 250000:
                continue
            paragraphs = [
                html.unescape(re.sub(r"<[^>]*>", "", x)).strip()
                for x in re.findall(r"<p\\b[^>]*>(.*?)</p>", raw, re.I | re.S)
            ]
            if len(paragraphs) < 3:
                continue
            date_match = re.search(r"\\b(\\d{2}\\.\\d{2}\\.\\d{4})\\b", paragraphs[0])
            if not date_match:
                continue
            try:
                day_date = datetime.strptime(date_match.group(1), "%d.%m.%Y").date()
                day = day_date.isoformat()
            except ValueError:
                continue
            stamp_match = re.search(r"(\\d{2}:\\d{2}).*?(\\d{2}\\.\\d{2}\\.\\d{4})", paragraphs[1])
            if not stamp_match:
                continue
            try:
                stamp = datetime.strptime(stamp_match.group(2) + " " + stamp_match.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=KYIV)
            except ValueError:
                continue
            groups = {}
            for p in paragraphs[2:]:
                m = re.search(r"Група\\s+(\\d+\\.\\d+)\\.\\s*(.*)", p, re.I)
                if not m or m.group(1) not in QUEUES:
                    continue
                queue, message = m.group(1), m.group(2)
                if "Електроенергія є" in message:
                    groups[queue] = ["yes"] * 24
                elif "Електроенергії немає" in message:
                    ranges = re.findall(r"з\\s+(\\d{2}:\\d{2})\\s+до\\s+(\\d{2}:\\d{2})", message)
                    if not ranges:
                        continue
                    # Half-hour intervals preserve exact official time boundaries.
                    halfhours = ["yes"] * 48
                    valid = True
                    for start, end in ranges:
                        try:
                            a_h, a_m = map(int, start.split(":"))
                            b_h, b_m = map(int, end.split(":"))
                        except ValueError:
                            valid = False
                            break
                        if a_h > 24 or b_h > 24 or a_m not in (0, 30) or b_m not in (0, 30):
                            valid = False
                            break
                        a, b = a_h * 2 + a_m // 30, b_h * 2 + b_m // 30
                        if not (0 <= a < b <= 48):
                            valid = False
                            break
                        for idx in range(a, b):
                            halfhours[idx] = "no"
                    if valid:
                        states = {( "yes", "yes"): "yes", ("no", "no"): "no",
                                  ("no", "yes"): "first", ("yes", "no"): "second"}
                        groups[queue] = [states[(halfhours[i], halfhours[i + 1])] for i in range(0, 48, 2)]
            if groups and (day not in updated_by_day or stamp > updated_by_day[day]):
                days[day] = groups
                updated_by_day[day] = stamp
    if not days:
        raise ValueError("Офіційний API не повернув розпізнаного графіка")
    latest = max(updated_by_day.values())
    return {"days": days, "source_updated": latest.astimezone(timezone.utc).isoformat(),
            "source_label": "Львівобленерго", "source": "https://poweron.loe.lviv.ua/",
            "source_type": "official"}


async def fetch_official(client):
    response = await client.get(OFFICIAL_URL, headers={"Accept": "application/ld+json, application/json", "User-Agent": "VartaUA/1.0"})
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("Завелика відповідь офіційного API")
    return parse_official(response.json())

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
                errors = []
                official = None
                try:
                    official = await fetch_official(client)
                except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                    errors.append("Офіційне джерело: " + str(exc))
                today = datetime.now(KYIV).date().isoformat()
                if official and today in official["days"]:
                    parsed = official
                else:
                    try:
                        response = await client.get(DATA_URL, headers={"User-Agent": "VartaUA/1.0", "Accept": "application/json"})
                        response.raise_for_status()
                        if len(response.content) > 2_000_000:
                            raise ValueError("Завеликий файл резервного джерела")
                        parsed = parse_source(response.json())
                        parsed["source"] = SOURCE
                        parsed["source_type"] = "aggregator"
                    except (httpx.HTTPError, ValueError, TypeError) as exc:
                        errors.append("Резервне джерело: " + str(exc))
                        if official:
                            parsed = official
                        else:
                            raise ValueError("; ".join(errors))
                _cache["data"] = parsed
                _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
                _cache["error"] = "; ".join(errors) if errors else None
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
            "queues": QUEUES, "source": data.get("source", SOURCE), "source_type": data.get("source_type", "aggregator"),
            "source_updated": data["source_updated"],
            "source_label": data["source_label"], "fetched_at": _cache["fetched_at"],
            "stale": stale, "error": _cache["error"],
            "note": "Плановий графік; аварійні відключення можуть відрізнятися."}
