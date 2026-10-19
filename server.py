
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
        if level in ("red", "yellow") and (previous["level"] != "red" or level == "red"):
            previous["level"] = level
    return result


async def poll_alerts():
    global status_data
    global last_updated
    global last_error
    global data_fresh

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
                response = await client.get(
                    ALERTS_URL,
                    headers={
                        "Authorization": f"Bearer {ALERTS_TOKEN}"
                    },
                )

                response.raise_for_status()

                parsed = parse_alerts(response.json())

                status_data = parsed
                last_updated = datetime.now(
                    timezone.utc
                ).isoformat()

                last_error = None
                data_fresh = True

            except Exception as error:
                last_error = str(error)
                data_fresh = False

                logger.warning(
                    "Alerts.in.ua error: %s",
                    repr(error),
                )

            await asyncio.sleep(20)


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
    }


@app.get("/api/status")
async def status():
    result = {
        region: value.copy()
        for region, value in status_data.items()
    }

    result["_meta"] = {
        "fresh": data_fresh,
        "updated_at": last_updated,
        "alerts_api_configured": bool(ALERTS_TOKEN),
        "error": last_error,
    }

    return result
