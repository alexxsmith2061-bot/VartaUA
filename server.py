import asyncio
import datetime as dt
import os
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse


# ==========================================
# VartaUA — конфігурація
# ==========================================

BASE = os.path.dirname(os.path.abspath(__file__))

ALERTS_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN", "").strip()

TG_API_ID = int(os.getenv("TG_API_ID") or 0)
TG_API_HASH = os.getenv("TG_API_HASH", "").strip()
TG_SESSION = os.getenv("TG_SESSION", "").strip()

TG_CHANNELS = [
    channel.strip()
    for channel in os.getenv(
        "TG_CHANNELS",
        "kpszsu,air_alert_ua,synegubov"
    ).split(",")
    if channel.strip()
]

# Перевіряємо API приблизно 3 рази на хвилину.
UPSTREAM_EVERY = 20

# Після цього часу без успішного оновлення
# статус не можна вважати актуальним.
STALE_AFTER = 90

# Тривалість додаткового попередження Telegram.
WARN_TTL = 600


# ==========================================
# Області України
# ==========================================

STEMS = {
    "Вінницька область": r"вінни",
    "Волинська область": r"волин|луцьк",
    "Дніпропетровська область": r"дніпр",
    "Донецька область": r"донеч|донецьк|краматорськ|слов'янськ",
    "Житомирська область": r"житомир",
    "Закарпатська область": r"закарпат|ужгород",
    "Запорізька область": r"запорі",
    "Івано-Франківська область": r"франків",
    "Київська область": r"київщин|київськ",
    "Кіровоградська область": r"кіровоград|кропивниц",
    "Львівська область": r"львів|львов",
    "Миколаївська область": r"миколаїв",
    "Одеська область": r"одещин|одес",
    "Полтавська область": r"полтав",
    "Рівненська область": r"рівн",
    "Сумська область": r"\bсум(?:щин|ськ|и\b|ах\b)",
    "Тернопільська область": r"тернопіл",
    "Харківська область": r"харків",
    "Херсонська область": r"херсон",
    "Хмельницька область": r"хмельни",
    "Черкаська область": r"черка",
    "Чернівецька область": r"чернівц|буковин",
    "Чернігівська область": r"чернігів",
    "м. Київ": r"\bкиїв(?!щин|ськ)\w*|\bкиєв\w*",
}

REGIONS = list(STEMS)

THREAT = re.compile(
    r"шахед|бпла|дрон|ракет|балістик|крилат|загроз|керован",
    re.IGNORECASE
)


# ==========================================
# Стан сервера
# ==========================================

STATE = {
    "active": {},
    "updated_at": 0.0,
    "warnings": {},
    "telegram_updated_at": 0.0,
    "error": "",
    "daily_changes": 0,
    "day": dt.date.today(),
}


# ==========================================
# Отримання статусів Alerts.in.ua
# ==========================================

async def poll_alerts():
    if not ALERTS_TOKEN:
        STATE["error"] = (
            "Не налаштовано ALERTS_IN_UA_TOKEN "
            "у змінних середовища Render."
        )

        print(STATE["error"])

        while True:
            await asyncio.sleep(30)

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            wait_seconds = UPSTREAM_EVERY

            try:
                response = await client.get(
                    "https://api.alerts.in.ua/v1/alerts/active.json",
                    headers={
                        "Authorization": f"Bearer {ALERTS_TOKEN}"
                    },
                )

                if response.status_code == 429:
                    STATE["error"] = (
                        "API обмежив частоту запитів. "
                        "Очікуємо перед повторною спробою."
                    )
                    await asyncio.sleep(60)
                    continue

                response.raise_for_status()

                payload = response.json()

                if isinstance(payload, dict):
                    alerts = payload.get("alerts", [])
                elif isinstance(payload, list):
                    alerts = payload
                else:
                    raise ValueError("Невідомий формат відповіді API")

                active = {}

                for alert in alerts:
                    if not isinstance(alert, dict):
                        continue

                    region = alert.get("location_oblast")
                    alert_type = alert.get("alert_type")

                    if (
                        alert_type == "air_raid"
                        and region in STEMS
                    ):
                        started = alert.get("started_at") or ""

                        if region not in active:
                            active[region] = started
                        elif started and (
                            not active[region]
                            or started < active[region]
                        ):
                            active[region] = started

                today = dt.date.today()

                if STATE["day"] != today:
                    STATE["day"] = today
                    STATE["daily_changes"] = 0

                new_alerts = [
                    region
                    for region in active
                    if region not in STATE["active"]
                ]

                STATE["daily_changes"] += len(new_alerts)
                STATE["active"] = active
                STATE["updated_at"] = time.time()
                STATE["error"] = ""

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                STATE["error"] = (
                    f"Помилка отримання даних: {type(exc).__name__}"
                )
                print("Alerts.in.ua error:", repr(exc))

            await asyncio.sleep(wait_seconds)


# ==========================================
# Додаткове джерело Telegram
# Працює лише якщо налаштовані всі змінні.
# ==========================================

async def telegram_listener():
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    while True:
        client = None

        try:
            client = TelegramClient(
                StringSession(TG_SESSION),
                TG_API_ID,
                TG_API_HASH,
            )

            await client.connect()

            if not await client.is_user_authorized():
                print(
                    "Telegram-сесія не авторизована. "
                    "Додаткове джерело вимкнено."
                )
                return

            @client.on(events.NewMessage(chats=TG_CHANNELS))
            async def on_message(event):
                message = (event.raw_text or "").lower()

                if not THREAT.search(message):
                    return

                for region, pattern in STEMS.items():
                    if re.search(pattern, message):
                        STATE["warnings"][region] = (
                            time.time() + WARN_TTL
                        )

            while client.is_connected():
                STATE["telegram_updated_at"] = time.time()
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print("Telegram error:", repr(exc))

        finally:
            if client:
                await client.disconnect()

        await asyncio.sleep(15)


# ==========================================
# Формування статусів для сайту
# ==========================================

def get_status():
    now = time.time()

    today = dt.date.today()

    if STATE["day"] != today:
        STATE["day"] = today
        STATE["daily_changes"] = 0

    fresh = (
        STATE["updated_at"] > 0
        and now - STATE["updated_at"] <= STALE_AFTER
    )

    result = {}

    for region in REGIONS:
        warning_is_active = (
            STATE["warnings"].get(region, 0) > now
        )

        if fresh and region in STATE["active"]:
            result[region] = {
                "state": "alert",
                "since": STATE["active"][region],
            }

        elif warning_is_active:
            result[region] = {
                "state": "warn",
            }

        elif fresh:
            result[region] = {
                "state": "calm",
            }

        else:
            result[region] = {
                "state": "unk",
            }

    result["_sources"] = {
        "alerts_in_ua": fresh,
        "telegram": (
            STATE["telegram_updated_at"] > 0
            and now - STATE["telegram_updated_at"] <= STALE_AFTER
        ),
    }

    result["_today"] = STATE["daily_changes"]

    result["_meta"] = {
        "updated_at": STATE["updated_at"] or None,
        "fresh": fresh,
        "alerts_api_configured": bool(ALERTS_TOKEN),
        "telegram_connected": (
            STATE["telegram_updated_at"] > 0
            and now - STATE["telegram_updated_at"] <= STALE_AFTER
        ),
        "error": STATE["error"],
        "source": "Alerts.in.ua",
    }

    return result


# ==========================================
# Запуск і завершення фонового опитування
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(poll_alerts())
    ]

    if TG_API_ID and TG_API_HASH and TG_SESSION:
        tasks.append(
            asyncio.create_task(telegram_listener())
        )

    yield

    for task in tasks:
        task.cancel()

    await asyncio.gather(
        *tasks,
        return_exceptions=True
    )


# ==========================================
# FastAPI
# ==========================================

app = FastAPI(
    title="VartaUA",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

NO_CACHE = {
    "Cache-Control": "no-store"
}


@app.get("/")
def read_root():
    return FileResponse(
        os.path.join(BASE, "index.html"),
        headers=NO_CACHE,
    )


@app.get("/api/status")
def api_status():
    return JSONResponse(
        get_status(),
        headers=NO_CACHE,
    )


@app.get("/api/health")
def api_health():
    meta = get_status()["_meta"]

    return JSONResponse({
        "ok": True,
        "alerts_api_configured": meta["alerts_api_configured"],
        "data_fresh": meta["fresh"],
        "updated_at": meta["updated_at"],
    })


@app.get("/settlements.json")
def settlements():
    path = os.path.join(BASE, "settlements.json")

    if os.path.exists(path):
        return FileResponse(
            path,
            headers=NO_CACHE,
        )

    return JSONResponse(
        {},
        status_code=404,
    )
