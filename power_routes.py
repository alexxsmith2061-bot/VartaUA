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
    diagnostics = {"menus": len(menus), "items": 0, "html_items": 0, "dated_items": 0, "parsed_groups": 0}
    for menu in menus:
        if not isinstance(menu, dict):
            continue
        for item in menu.get("menuItems", []):
            diagnostics["items"] += 1
            if not isinstance(item, dict):
                continue
            raw = item.get("rawHtml", "")
            if not isinstance(raw, str) or len(raw) > 250000:
                continue
            diagnostics["html_items"] += 1
            paragraphs = [
                html.unescape(re.sub(r"<[^>]*>", "", x)).strip()
                for x in re.findall(r"<p\b[^>]*>(.*?)</p>", raw, re.I | re.S)
            ]
            if len(paragraphs) < 3:
                continue
            date_match = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", paragraphs[0])
            if not date_match:
                continue
            try:
                day_date = datetime.strptime(date_match.group(1), "%d.%m.%Y").date()
                day = day_date.isoformat()
            except ValueError:
                continue
            stamp_match = re.search(r"(\d{2}:\d{2}).*?(\d{2}\.\d{2}\.\d{4})", paragraphs[1])
            if not stamp_match:
                continue
            try:
                stamp = datetime.strptime(stamp_match.group(2) + " " + stamp_match.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=KYIV)
            except ValueError:
                continue
            diagnostics["dated_items"] += 1
            groups = {}
            for p in paragraphs[2:]:
                m = re.search(r"Група\s+(\d+\.\d+)\.\s*(.*)", p, re.I)
                if not m or m.group(1) not in QUEUES:
                    continue
                queue, message = m.group(1), m.group(2)
                if "Електроенергія є" in message:
                    groups[queue] = ["yes"] * 24
                elif "Електроенергії немає" in message:
                    ranges = re.findall(r"з\s+(\d{2}:\d{2})\s+до\s+(\d{2}:\d{2})", message)
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
            diagnostics["parsed_groups"] += len(groups)
            if groups and (day not in updated_by_day or stamp > updated_by_day[day]):
                days[day] = groups
                updated_by_day[day] = stamp
    if not days:
        raise ValueError("Немає розпізнаних графіків в офіційній відповіді (" + ", ".join(f"{k}={v}" for k, v in diagnostics.items()) + ")")
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
                if official is None:
                    raise ValueError("; ".join(errors) or "Офіційні графіки недоступні")
                parsed = official
                _cache["data"] = parsed
                _cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
                _cache["error"] = "; ".join(errors) if errors else None
        except (httpx.HTTPError, ValueError) as exc:
            _cache["data"] = None
            _cache["error"] = str(exc)


# Official address directory, fetched server-side because the provider restricts browser CORS.
_directory_cache = {}
_directory_lock = asyncio.Lock()

async def _official_directory(kind: str, city_id: int | None = None):
    if kind not in ("cities", "streets"):
        raise HTTPException(400, "Невідомий довідник")
    if kind == "streets" and (city_id is None or city_id < 1):
        raise HTTPException(400, "Потрібен код населеного пункту")
    key = (kind, city_id)
    now = time.monotonic()
    cached = _directory_cache.get(key)
    if cached and now - cached[0] < 86400:
        return cached[1]
    async with _directory_lock:
        cached = _directory_cache.get(key)
        if cached and time.monotonic() - cached[0] < 86400:
            return cached[1]
        url = "https://power-api.loe.lviv.ua/api/pw_" + kind
        params = {"pagination": "false"}
        if kind == "cities":
            params["otg.id"] = ""
        else:
            params["city.id"] = str(city_id)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(url, params=params, headers={"Accept": "application/ld+json, application/json"})
                response.raise_for_status()
                if len(response.content) > 3_000_000:
                    raise ValueError("Завеликий довідник")
                body = response.json()
            entries = body.get("hydra:member") if isinstance(body, dict) else body
            if not isinstance(entries, list):
                raise ValueError("Неправильний формат довідника")
            result = []
            for row in entries:
                if not isinstance(row, dict) or not isinstance(row.get("id"), int) or not isinstance(row.get("name"), str):
                    continue
                item = {"id": row["id"], "name": row["name"]}
                # Different API representations can embed the OTG as an object,
                # a numeric identifier, or an API Platform IRI.
                otg = row.get("otg")
                otg_id = None
                if isinstance(otg, dict):
                    otg_id = otg.get("id")
                    if otg_id is None:
                        otg_id = otg.get("@id")
                elif isinstance(otg, (int, str)):
                    otg_id = otg
                if otg_id is None:
                    otg_id = row.get("otgId", row.get("otg_id"))
                if isinstance(otg_id, str):
                    match = re.fullmatch(r"(?:/api/pw_otgs/)?(\d+)", otg_id)
                    otg_id = int(match.group(1)) if match else None
                if isinstance(otg_id, int) and otg_id > 0:
                    item["otg_id"] = otg_id
                result.append(item)
            if not result:
                raise ValueError("Довідник порожній")
            _directory_cache[key] = (time.monotonic(), result)
            return result
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            if cached:
                return cached[1]
            raise HTTPException(503, "Офіційний адресний довідник тимчасово недоступний")


@router.get("/api/power/city-diagnostics")
async def power_city_diagnostics(city_id: int):
    """Safe diagnostics: inspect public directory metadata without account records."""
    if city_id < 1:
        raise HTTPException(400, "Некоректний код міста")
    result = {"city_id": city_id}
    try:
        cities = await _official_directory("cities")
        city = next((item for item in cities if item["id"] == city_id), None)
        result["directory_found"] = city is not None
        result["directory_otg_id"] = city.get("otg_id") if city else None
    except HTTPException:
        result["directory_error"] = "Довідник недоступний"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://power-api.loe.lviv.ua/api/pw_cities",
                params={"id": city_id, "pagination": "false"},
                headers={"Accept": "application/ld+json, application/json"})
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError("Завелика відповідь")
            payload = response.json()
        rows = payload.get("hydra:member") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("Невідомий формат")
        matching = next((row for row in rows if isinstance(row, dict) and row.get("id") == city_id), None)
        result["direct_found"] = matching is not None
        if matching:
            result["field_names"] = sorted(matching.keys())[:50]
            for key in ("otg", "otgId", "otg_id", "territorialCommunity"):
                value = matching.get(key)
                if isinstance(value, dict):
                    result[key] = {"field_names": sorted(value.keys())[:20], "id": value.get("id"), "iri": value.get("@id")}
                elif isinstance(value, (int, str)):
                    result[key] = str(value)[:100]
    except (httpx.HTTPError, ValueError, TypeError):
        result["direct_error"] = "Не вдалося отримати запис"
    return result


@router.get("/api/power/cities")
async def power_cities():
    return {"items": await _official_directory("cities")}


@router.get("/api/power/streets")
async def power_streets(city_id: int):
    return {"items": await _official_directory("streets", city_id)}


@router.get("/api/power/houses")
async def power_houses(city_id: int, street_id: int):
    """Official address account search. Only expose public house/queue mapping when explicit."""
    if city_id < 1 or street_id < 1:
        raise HTTPException(400, "Некоректна адреса")
    key = ("houses", city_id, street_id)
    cached = _directory_cache.get(key)
    if cached and time.monotonic() - cached[0] < 1800:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://power-api.loe.lviv.ua/api/pw_accounts",
                params={"pagination": "false", "city.id": city_id, "street.id": street_id},
                headers={"Accept": "application/ld+json, application/json"})
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise ValueError("Завелика відповідь")
            payload = response.json()
        rows = payload.get("hydra:member") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("Невідомий формат")
        by_house = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            house = row.get("buildingName")
            if not isinstance(house, (str, int)) or not str(house).strip():
                continue
            house = str(house).strip()
            raw_queue = row.get("chergGpv")
            queue = str(raw_queue).strip() if raw_queue is not None else None
            if queue not in QUEUES:
                queue = None
            by_house.setdefault(house, set()).add(queue)
        houses = []
        for house, queues in by_house.items():
            valid = {q for q in queues if q is not None}
            # Multiple conflicting or missing values must not produce a guessed queue.
            resolved = next(iter(valid)) if len(valid) == 1 and None not in queues else None
            houses.append({"house": house, "queue": resolved})
        result = {"houses": houses, "count": len(rows),
                  "verified": bool(houses), "source": "Львівобленерго"}
        _directory_cache[key] = (time.monotonic(), result)
        return result
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Офіційний сервіс будинків не відповідає. Чергу не визначено.")



@router.get("/api/power/diagnostics")
async def power_diagnostics():
    """Public schedule and directory metadata; no personal account records."""
    results = {}
    urls = {"schedule": OFFICIAL_URL,
            "cities": "https://power-api.loe.lviv.ua/api/pw_cities?pagination=false&otg.id="}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for name, url in urls.items():
            try:
                response = await client.get(url, headers={"Accept": "application/ld+json, application/json"})
                info = {"status": response.status_code, "content_type": response.headers.get("content-type", "")[:90]}
                if response.is_success:
                    payload = response.json()
                    rows = payload.get("hydra:member", []) if isinstance(payload, dict) else payload
                    info["count"] = len(rows) if isinstance(rows, list) else None
                    if name == "schedule" and isinstance(rows, list):
                        samples = []
                        for menu in rows[:3]:
                            if not isinstance(menu, dict):
                                continue
                            for item in menu.get("menuItems", [])[:6]:
                                if not isinstance(item, dict):
                                    continue
                                raw = item.get("rawHtml", "")
                                if not isinstance(raw, str):
                                    raw = ""
                                plain = html.unescape(re.sub(r"<[^>]+>", " ", raw))
                                plain = " ".join(plain.split())
                                samples.append({"name": str(item.get("name", ""))[:80],
                                                "html_length": len(raw), "text_preview": plain[:400],
                                                "fields": sorted(item.keys())[:35],
                                                "field_shapes": {str(k)[:50]: ("list:"+str(len(v)) if isinstance(v,list) else "object:"+",".join(list(v.keys())[:8]) if isinstance(v,dict) else "string:"+str(len(v)) if isinstance(v,str) else type(v).__name__) for k,v in item.items() if k not in ("rawHtml",)},
                                                "menu_fields": sorted(menu.keys())[:20]})
                        info["samples"] = samples
                    elif name == "cities" and isinstance(rows, list) and rows and isinstance(rows[0], dict):
                        info["fields"] = sorted(rows[0].keys())[:20]
                results[name] = info
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                results[name] = {"error": type(exc).__name__}
    return {"provider": "Львівобленерго", "results": results}


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
                "error": _cache["error"] or "Джерело недоступне", "source": "https://poweron.loe.lviv.ua/", "source_type": "official",
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


# Public informational feed. This does not infer outage times from Telegram posts.
TELEGRAM_PUBLIC_URL = "https://t.me/s/lvivoblenergo"
_news_cache = {"checked": 0.0, "items": [], "error": None}
_news_lock = asyncio.Lock()

@router.get("/api/power/news")
async def power_official_news():
    """Recent public posts from the official channel; informational, not an outage schedule."""
    if time.monotonic() - _news_cache["checked"] < 300:
        return {"source": TELEGRAM_PUBLIC_URL, "items": _news_cache["items"],
                "available": bool(_news_cache["items"]), "error": _news_cache["error"], "diagnostic": _news_cache.get("diagnostic")}
    async with _news_lock:
        if time.monotonic() - _news_cache["checked"] < 300:
            return {"source": TELEGRAM_PUBLIC_URL, "items": _news_cache["items"],
                    "available": bool(_news_cache["items"]), "error": _news_cache["error"], "diagnostic": _news_cache.get("diagnostic")}
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                response = await client.get(TELEGRAM_PUBLIC_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; VartaUA/1.0)"})
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError("Завелика сторінка")
                page = response.text
            # Telegram public preview marks each message with data-post="lvivoblenergo/123".
            blocks = re.split(r'(?=<div[^>]*class="[^"]*tgme_widget_message_wrap)', page)
            items = []
            for block in blocks:
                match = re.search(r'data-post="lvivoblenergo/(\\d+)"', block)
                if not match:
                    continue
                post_id = int(match.group(1))
                body = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
                if not body:
                    continue
                cleaned = re.sub(r'<br\\s*/?>', '\\n', body.group(1), flags=re.I)
                cleaned = html.unescape(re.sub(r'<[^>]+>', '', cleaned)).strip()
                if not cleaned:
                    continue
                items.append({"id": post_id, "text": cleaned[:1600],
                              "url": f"https://t.me/lvivoblenergo/{post_id}"})
            items = sorted({item["id"]: item for item in items}.values(), key=lambda item: item["id"], reverse=True)[:15]
            if not items:
                raise ValueError("Публічні повідомлення не вдалося прочитати")
            _news_cache.update(checked=time.monotonic(), items=items, error=None, diagnostic=None)
        except (httpx.HTTPError, ValueError) as exc:
            reason = ("http_" + str(exc.response.status_code)) if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
            _news_cache.update(checked=time.monotonic(), error="Не вдалося прочитати публічну стрічку", diagnostic=reason)
        return {"source": TELEGRAM_PUBLIC_URL, "items": _news_cache["items"],
                "available": bool(_news_cache["items"]), "error": _news_cache["error"], "diagnostic": _news_cache.get("diagnostic")}


@router.get("/api/power/outages")
async def power_outages(city_id: int, street_id: int):
    """Registered outages for the selected street, not a house-level power meter."""
    if city_id < 1 or street_id < 1:
        raise HTTPException(400, "Некоректна адреса")
    # Resolve OTG from the official city directory, never from user-supplied values.
    otg_id = None
    try:
        cities = await _official_directory("cities")
        city = next((item for item in cities if item["id"] == city_id), None)
        if city is None:
            raise HTTPException(404, "Населений пункт відсутній в офіційному довіднику")
        otg_id = city.get("otg_id")
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        # The provider supports city+street filters without an OTG.
        pass
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://power-api.loe.lviv.ua/api/pw_accidents",
                params={"page": 1, "city.id": city_id, "street.id": street_id,
                        **({"otg.id": otg_id} if otg_id is not None else {})},
                headers={"Accept": "application/ld+json, application/json"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика відповідь")
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Неправильний формат")
        members = payload.get("hydra:member")
        total = payload.get("hydra:totalItems")
        if not isinstance(members, list) or not isinstance(total, int) or total < 0:
            raise ValueError("Неповна відповідь")
        # Only publish the field names of records, never raw accident objects or account details.
        record_fields = sorted(set().union(*(set(item.keys()) for item in members[:5] if isinstance(item, dict))))[:60] if total else []
        return {"available": True, "scope": "street", "registered_count": total,
                "record_fields": record_fields, "otg_filter_used": otg_id is not None,
                "status": "none_found" if total == 0 else "records_found",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "source": "Львівобленерго",
                "note": "Кількість записів за вулицею; не підтверджує наявність напруги в будинку."}
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося перевірити зареєстровані відключення")


@router.get("/api/power/outage-schema")
async def power_outage_schema(otg_id: int):
    """One bounded official query per request; disclose schema only, never accident records."""
    if otg_id < 1:
        raise HTTPException(400, "Некоректний код громади")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://power-api.loe.lviv.ua/api/pw_accidents",
                params={"page": 1, "otg.id": otg_id},
                headers={"Accept": "application/ld+json, application/json"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика відповідь")
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Невідомий формат")
        members = payload.get("hydra:member")
        total = payload.get("hydra:totalItems")
        if not isinstance(members, list) or not isinstance(total, int):
            raise ValueError("Неповна відповідь")
        sample = [row for row in members[:5] if isinstance(row, dict)]
        fields = sorted(set().union(*(set(row.keys()) for row in sample))) if sample else []
        shapes = {}
        for field in fields[:70]:
            values = [row.get(field) for row in sample if field in row]
            shapes[field] = sorted(set("object" if isinstance(v, dict) else "array" if isinstance(v, list) else "null" if v is None else type(v).__name__ for v in values))
        # Aggregate codes and format metadata only; never publish raw street/building values.
        import collections
        codes = {}
        for key in ("typeOff", "switchSubReason"):
            counter = collections.Counter(str(row[key]) for row in sample if isinstance(row.get(key), int))
            codes[key] = dict(counter.most_common(15))
        formats = {}
        for key in ("dateEvent", "datePlanIn", "buildingNames", "koment"):
            values = [row.get(key) for row in sample if isinstance(row.get(key), str)]
            formats[key] = {"nonempty_in_sample": sum(bool(v.strip()) for v in values),
                            "max_length": max((len(v) for v in values), default=0)}
        # Diagnose whether the field contains numbers, masked placeholders, or free text.
        # Return only aggregate counts; never reveal address strings.
        building_summary = {"sampled": 0, "empty": 0, "contains_ascii_digits": 0,
                            "contains_unicode_digits": 0, "comma_separated": 0,
                            "single_token": 0, "only_punctuation_or_spaces": 0}
        for row in sample:
            value = row.get("buildingNames")
            if not isinstance(value, str):
                continue
            building_summary["sampled"] += 1
            if not value.strip():
                building_summary["empty"] += 1
            if any("0" <= ch <= "9" for ch in value):
                building_summary["contains_ascii_digits"] += 1
            if any(ch.isdigit() for ch in value):
                building_summary["contains_unicode_digits"] += 1
            if "," in value:
                building_summary["comma_separated"] += 1
            if len(value.split()) == 1:
                building_summary["single_token"] += 1
            if not any(ch.isalnum() for ch in value):
                building_summary["only_punctuation_or_spaces"] += 1
        address_formats = []
        for row in sample:
            value = row.get("buildingNames")
            if not isinstance(value, str):
                continue
            address_formats.append({
                "length": len(value),
                "has_comma": "," in value,
                "has_semicolon": ";" in value,
                "has_newline": "\\n" in value,
                "has_slash": "/" in value,
                "has_letters": bool(re.search(r"[А-Яа-яІіЇїЄєA-Za-z]", value)),
                "has_digits": bool(re.search(r"\\d", value)),
                "looks_like_json": value.lstrip().startswith(("[", "{")),
                "approx_comma_parts": min(value.count(",") + 1, 100),
                "approx_semicolon_parts": min(value.count(";") + 1, 100),
            })
        return {"available": True, "otg_id": otg_id, "total_items": total,
                "sample_size": len(sample), "page_items": len(members), "field_types": shapes, "sample_codes": codes, "sample_formats": formats, "building_format_samples": address_formats, "building_summary": building_summary,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "note": "Лише структура першої сторінки, без значень записів"}
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося отримати структуру відключень")


@router.get("/api/power/schedule-source-check")
async def power_schedule_source_check():
    """Check a candidate external schedule API without treating it as official."""
    url = "https://dkr.ova.net.ua/api/schedule"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика відповідь")
            payload = response.json()
        if isinstance(payload, dict):
            keys = sorted(str(k) for k in payload.keys())[:40]
            shapes = {str(k): type(v).__name__ for k, v in list(payload.items())[:40]}
            groups = payload.get("groups")
            group_keys = sorted(str(k) for k in groups.keys())[:100] if isinstance(groups, dict) else []
            group_types = {str(k): type(v).__name__ for k, v in list(groups.items())[:20]} if isinstance(groups, dict) else {}
            return {"available": True, "candidate_source": url, "official": False,
                    "root_type": "object", "root_keys": keys, "value_types": shapes,
                    "fetched_at": payload.get("fetched_at") if isinstance(payload.get("fetched_at"), str) else None,
                    "groups_count": len(groups) if isinstance(groups, dict) else None,
                    "group_keys": group_keys, "group_value_types": group_types,
                    "expected_queues_present": sorted(q for q in QUEUES if isinstance(groups, dict) and (q in groups or "GPV" + q in groups)),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "note": "Тільки діагностика формату; графік не використовується без перевірки актуальності"}
        if isinstance(payload, list):
            return {"available": True, "candidate_source": url, "official": False,
                    "root_type": "array", "item_count": len(payload),
                    "first_item_keys": sorted(payload[0].keys())[:40] if payload and isinstance(payload[0], dict) else [],
                    "checked_at": datetime.now(timezone.utc).isoformat()}
        raise ValueError("Непідтримуваний формат")
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Кандидатне джерело недоступне або повернуло невідомий формат")


@router.get("/api/power/svitlo-source-check")
async def power_svitlo_source_check():
    """Inspect public page metadata only. Never assume third-party schedule availability."""
    url = "https://svitlo.day/"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; VartaUA/1.0)"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика сторінка")
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                raise ValueError("Сторінка не HTML")
            page = response.text
        scripts = re.findall(r"<script[^>]+src=[\u0027\u0022]([^\u0027\u0022]+)", page, re.I)
        scripts = [src[:200] for src in scripts if src.startswith("/") or src.startswith("https://svitlo.day/")][:20]
        return {"available": True, "source": url, "official": False,
                "html_bytes": len(response.content), "script_count": len(scripts),
                "script_paths": scripts,
                "has_next_data": "__NEXT_DATA__" in page,
                "has_nuxt_data": "__NUXT__" in page,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "note": "Діагностика відкритої сторінки, не підтвердження наявності графіка"}
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося прочитати відкриту сторінку svitlo.day")


@router.get("/api/power/svitlo-api-check")
async def power_svitlo_api_check():
    """Inspect public JS for API route literals; never return source code or secrets."""
    url = "https://svitlo.day/app.js?v=67f8cf68"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; VartaUA/1.0)"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завеликий JavaScript")
            script = response.text
        # Only relative, literal API routes. Do not disclose arbitrary URLs or JS contents.
        candidates = set(re.findall(r"""["'](/api/[a-zA-Z0-9_/?=&.{}:-]{1,140})["']""", script))
        fetch_literals = set(re.findall(r"""fetch\s*\(\s*["'](/[^"' ]{1,140})["']""", script))
        routes = sorted(candidates | fetch_literals)[:60]
        return {"available": True, "source": "svitlo.day", "official": False,
                "js_bytes": len(response.content), "relative_routes": routes,
                "fetch_calls_count": len(re.findall(r"\bfetch\s*\(", script)),
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "note": "Лише статичні відносні шляхи; динамічні запити можуть бути не знайдені"}
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося перевірити відкритий JavaScript")


@router.get("/api/power/telegram-source-check")
async def power_telegram_source_check():
    """Read-only check of the public Telegram preview; no user sessions or credentials."""
    url = "https://t.me/s/lviv_bezsvitla"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; VartaUA/1.0)"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика сторінка")
            page = response.text
        ids = re.findall(r'data-post="(lviv_bezsvitla/[0-9]+)"', page)
        dates = re.findall(r'<time[^>]*datetime="([^"]+)"', page)
        return {
            "available": True, "source": "https://t.me/lviv_bezsvitla",
            "public_preview": url, "official": False,
            "message_count": len(ids),
            "latest_message_id": ids[-1] if ids else None,
            "latest_message_url": "https://t.me/" + ids[-1] if ids else None,
            "latest_message_date": dates[-1] if dates else None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "Перевірка публічного прев'ю; не підтверджує актуальність графіків або дозвіл на републікацію"
        }
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Публічне прев'ю Telegram недоступне з сервера")


@router.get("/api/power/telegram-changes-check")
async def power_telegram_changes_check():
    """Parse public channel messages for queue mentions, without applying schedules."""
    url = "https://t.me/s/lviv_bezsvitla"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; VartaUA/1.0)"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика сторінка")
            page = response.text
        blocks = re.split(r'(?=<div[^>]+class="[^"]*tgme_widget_message_wrap)', page)
        messages = []
        for block in blocks:
            match = re.search(r'data-post="(lviv_bezsvitla/[0-9]+)"', block)
            if not match:
                continue
            body_match = re.search(r'<div[^>]+class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
            if not body_match:
                continue
            body = re.sub(r'<[^>]+>', " ", body_match.group(1))
            body = html.unescape(body)
            queues = sorted(set(re.findall(r'(?<![0-9])([1-6][.]?[12])(?![0-9])', body)))
            normalized = sorted(set(q if "." in q else q[0] + "." + q[1] for q in queues))
            times = re.findall(r'(?<![0-9])(?:[01]?[0-9]|2[0-3]):[0-5][0-9](?![0-9])', body)
            date_match = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            if normalized:
                messages.append({
                    "message_url": "https://t.me/" + match.group(1),
                    "published_at": date_match.group(1) if date_match else None,
                    "queues": normalized, "times_mentioned": times[:30],
                    "has_change_words": bool(re.search(r'змін|оновлен|було|стало|новий|старий', body, re.I))
                })
        return {
            "available": True, "source": "https://t.me/lviv_bezsvitla",
            "official": False, "matched_count": len(messages),
            "messages": messages[-20:],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "Черги й години лише згадані в тексті; це НЕ перевірені інтервали графіка і не застосовуються до поточного дня"
        }
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося прочитати повідомлення Telegram")


@router.get("/api/power/telegram-queue-check")
async def power_telegram_queue_check(queue: str = "4.2"):
    """Inspect queue-specific message sections, without claiming a live schedule."""
    if queue not in QUEUES:
        raise HTTPException(400, "Невідома черга")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get("https://t.me/s/lviv_bezsvitla",
                                        headers={"User-Agent": "Mozilla/5.0 (compatible; VartaUA/1.0)"})
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Завелика сторінка")
            page = response.text
        blocks = re.split(r'(?=<div[^>]+class="[^"]*tgme_widget_message_wrap)', page)
        found = []
        for block in blocks:
            post = re.search(r'data-post="(lviv_bezsvitla/[0-9]+)"', block)
            body_match = re.search(r'<div[^>]+class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
            if not post or not body_match:
                continue
            body_html = re.sub(r'<br\\s*/?>', "\\n", body_match.group(1), flags=re.I)
            body_html = re.sub(r'</(?:p|div)>', "\\n", body_html, flags=re.I)
            body = html.unescape(re.sub(r'<[^>]+>', " ", body_html))
            pattern = r'(?<![0-9])' + re.escape(queue) + r'(?![0-9])'
            matches = list(re.finditer(pattern, body))
            if not matches:
                continue
            date_match = re.search(r'<time[^>]*datetime="([^"]+)"', block)
            # Short surrounding text is diagnostic evidence, NOT a parsed schedule.
            snippets = [body[max(0, m.start()-100):min(len(body), m.end()+260)].strip() for m in matches[:5]]
            found.append({"message_url": "https://t.me/" + post.group(1),
                          "published_at": date_match.group(1) if date_match else None,
                          "queue": queue, "mentions": len(matches),
                          "context_samples": snippets})
        return {"source": "https://t.me/lviv_bezsvitla", "official": False,
                "queue": queue, "messages": found[-20:],
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "note": "Фрагменти тексту для перевірки формату, не підтверджений графік"}
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося перевірити повідомлення каналу")
