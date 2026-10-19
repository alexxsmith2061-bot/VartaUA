
import os
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse

from power_routes import router as power_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vartaua")

app = FastAPI(title="VartaUA")

# Підключення модуля електроенергії
app.include_router(power_router)

ALERTS_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN", "").strip()

ALERTS_URL = "https://api.alerts.in.ua/v1/alerts/active.json"

REGIONS = [
    "Автономна Республіка Крим",
    "Вінницька область",
    "Волинська область",
    "Дніпропетровська область",
    "Донецька область",
    "Житомирська область",
    "Закарпатська область",
    "Запорізька область",
    "Івано-Франківська область",
    "Київська область",
    "Кіровоградська область",
    "Луганська область",
    "Львівська область",
    "Миколаївська область",
    "Одеська область",
    "Полтавська область",
    "Рівненська область",
    "Сумська область",
    "Тернопільська область",
    "Харківська область",
    "Херсонська область",
    "Хмельницька область",
    "Черкаська область",
    "Чернівецька область",
    "Чернігівська область",
    "м. Київ",
    "м. Севастополь",
]

status_data = {
    region: {"state": "unk"}
    for region in REGIONS
}

last_updated = None
last_error = None
data_fresh = False
last_audit = {}
last_alert_records = []
next_poll_seconds = 120
rate_limit_failures = 0
last_http_status = None
last_modified = None
last_successful_check = None


def normalize_region(name):
    if not isinstance(name, str):
        return ""

    name = name.strip()

    if name in REGIONS:
        return name

    if name + " область" in REGIONS:
        return name + " область"

    return name


def parse_alerts(payload):
    """Aggregate active air-raid alerts without treating district alerts as whole-oblast alerts."""
    result = {region: {"state": "calm", "scope": "none", "level": None}
              for region in REGIONS}
    if isinstance(payload, dict):
        alerts = payload.get("alerts")
    elif isinstance(payload, list):
        alerts = payload
    else:
        raise ValueError("Невідомий формат відповіді API")
    if not isinstance(alerts, list):
        raise ValueError("Немає списку alerts")

    for item in alerts:
        if not isinstance(item, dict):
            continue
        if item.get("alert_type") != "air_raid":
            continue
        if item.get("finished_at") is not None:
            continue
        location_type = item.get("location_type")
        oblast = normalize_region(item.get("location_oblast") or "")
        title = normalize_region(item.get("location_title") or "")
        region = title if location_type == "oblast" else oblast
        if region not in result:
            continue
        whole = location_type == "oblast" or title in ("м. Київ", "м. Севастополь")
        previous = result[region]
        if whole or previous["state"] != "alert":
            previous["state"] = "alert"
            previous["scope"] = "oblast" if whole else "partial"
        if whole:
            previous["scope"] = "oblast"
        level = item.get("alert_level")
        if level not in ("red", "yellow"):
            level = "unknown"
        if previous["level"] != "red" and (level == "red" or previous["level"] is None):
            previous["level"] = level
        elif previous["level"] == "unknown" and level == "yellow":
            previous["level"] = level
    return result


async def poll_alerts():
    global status_data
    global last_updated
    global last_error
    global data_fresh
    global last_audit
    global last_alert_records
    global next_poll_seconds
    global last_modified
    global last_successful_check
    global rate_limit_failures
    global last_http_status

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            if not ALERTS_TOKEN:
                last_error = (
                    "Не налаштовано ALERTS_IN_UA_TOKEN "
                    "у змінних середовища Render."
                )
                data_fresh = False
                await asyncio.sleep(30)
                continue

            try:
                headers = {"Authorization": f"Bearer {ALERTS_TOKEN}"}
                if last_modified:
                    headers["If-Modified-Since"] = last_modified
                response = await client.get(ALERTS_URL, headers=headers)
                last_http_status = response.status_code
                response.raise_for_status()
                last_successful_check = datetime.now(timezone.utc).isoformat()
                if response.status_code == 304:
                    last_error = None
                    data_fresh = True
                    next_poll_seconds = 120
                    await asyncio.sleep(next_poll_seconds)
                    continue
                last_modified = response.headers.get("Last-Modified") or None

                payload = response.json()
                parsed = parse_alerts(payload)
                last_alert_records = [a for a in (payload.get("alerts", []) if isinstance(payload, dict) else payload) if isinstance(a, dict)]
                entries = payload.get("alerts", []) if isinstance(payload, dict) else payload
                last_audit = {
                    "source": ALERTS_URL,
                    "received_entries": len(entries),
                    "received_air_raid": sum(1 for a in entries if isinstance(a, dict) and a.get("alert_type") == "air_raid"),
                    "mapped_regions": sum(1 for a in parsed.values() if a["state"] == "alert"),
                    "red": sum(1 for a in parsed.values() if a["state"] == "alert" and a["level"] == "red"),
                    "yellow": sum(1 for a in parsed.values() if a["state"] == "alert" and a["level"] == "yellow"),
                    "unknown_level": sum(1 for a in parsed.values() if a["state"] == "alert" and a["level"] not in ("red", "yellow")),
                }
                status_data = parsed
                last_updated = datetime.now(
                    timezone.utc
                ).isoformat()

                last_error = None
                data_fresh = True
                next_poll_seconds = 120
                rate_limit_failures = 0

            except httpx.HTTPStatusError as error:
                last_error = str(error)
                data_fresh = False
                last_http_status = error.response.status_code
                if error.response.status_code == 429:
                    rate_limit_failures += 1
                    retry = error.response.headers.get("Retry-After", "")
                    try:
                        next_poll_seconds = max(900 * (2 ** min(rate_limit_failures - 1, 3)), int(retry) + 60)
                    except (ValueError, TypeError):
                        next_poll_seconds = 900 * (2 ** min(rate_limit_failures - 1, 3))
                else:
                    next_poll_seconds = 360
                logger.warning("Alerts.in.ua HTTP %s; next attempt in %s seconds", error.response.status_code, next_poll_seconds)
            except Exception as error:
                last_error = str(error)
                data_fresh = False

                next_poll_seconds = max(120, next_poll_seconds)
                logger.warning(
                    "Alerts.in.ua error: %s",
                    repr(error),
                )

            await asyncio.sleep(next_poll_seconds)


@app.on_event("startup")
async def startup():
    app.state.alerts_task = asyncio.create_task(
        poll_alerts()
    )


@app.on_event("shutdown")
async def shutdown():
    task = getattr(
        app.state,
        "alerts_task",
        None,
    )

    if task:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


@app.get("/")
async def home():
    return FileResponse("index.html")


@app.get("/api/build")
async def build_info():
    return {"app": "VartaUA", "build_marker": "safe-build-v3",
            "power_router_imported": True}


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "alerts_api_configured": bool(ALERTS_TOKEN),
        "data_fresh": data_fresh,
        "updated_at": last_updated,
        "error": last_error,
        "last_successful_check": last_successful_check,
        "next_poll_seconds": next_poll_seconds,
        "last_http_status": last_http_status,
    }


@app.get("/api/status")
async def status():
    result = {
        region: value.copy()
        for region, value in status_data.items()
    }

    result["_meta"] = {
        "audit": last_audit,
        "next_poll_seconds": next_poll_seconds,
        "last_http_status": last_http_status,
        "rate_limit_failures": rate_limit_failures,
        "last_successful_check": last_successful_check,
        "fresh": data_fresh,
        "updated_at": last_updated,
        "alerts_api_configured": bool(ALERTS_TOKEN),
        "error": last_error,
    }

    return result


@app.get("/api/alerts/details")
async def alert_details():
    """Last successful upstream response, including district/community and non-air-raid alerts."""
    return {"fresh": data_fresh, "updated_at": last_updated,
            "source": "Alerts.in.ua", "records": last_alert_records,
            "count": len(last_alert_records), "error": last_error}
