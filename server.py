import asyncio, datetime as dt, os, re, time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

BASE = os.path.dirname(os.path.abspath(__file__))
ALERTS_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN", "")
TG_API_ID = int(os.getenv("TG_API_ID") or 0)
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION = os.getenv("TG_SESSION", "")
TG_CHANNELS = [c.strip() for c in os.getenv("TG_CHANNELS", "kpszsu,air_alert_ua,synegubov").split(",") if c.strip()]
UPSTREAM_EVERY = 5   # с; перевірте ліміти alerts.in.ua
STALE_AFTER = 30     # с без свіжих даних -> "невідомо", а не "тиша"
WARN_TTL = 600       # с тримати 🟡 після повідомлення з Telegram

STEMS = {
 "Вінницька область": r"вінни", "Волинська область": r"волин|луцьк", "Дніпропетровська область": r"дніпр",
 "Донецька область": r"донеч|донецьк|краматорськ|слов'янськ", "Житомирська область": r"житомир",
 "Закарпатська область": r"закарпат|ужгород", "Запорізька область": r"запорі",
 "Івано-Франківська область": r"франків", "Київська область": r"київщин|київськ",
 "Кіровоградська область": r"кіровоград|кропивниц", "Львівська область": r"львів|львов",
 "Миколаївська область": r"миколаїв", "Одеська область": r"одещин|одес", "Полтавська область": r"полтав",
 "Рівненська область": r"рівн", "Сумська область": r"\bсум(?:щин|ськ|и\b|ах\b)", "Тернопільська область": r"тернопіл",
 "Харківська область": r"харків", "Херсонська область": r"херсон", "Хмельницька область": r"хмельни",
 "Черкаська область": r"черка", "Чернівецька область": r"чернівц|буковин", "Чернігівська область": r"чернігів",
 "м. Київ": r"\bкиїв(?!щин|ськ)\w*|\bкиєв\w*",
}
REGIONS = list(STEMS)
THREAT = re.compile(r"шахед|бпла|дрон|ракет|балістик|крилат|загроз|керован", re.I)
S = {"act": {}, "ts": 0.0, "warn": {}, "tg_ts": 0.0, "today": 0, "day": dt.date.today()}


async def poll_alerts():
    async with httpx.AsyncClient(timeout=4) as c:
        while True:
            wait = UPSTREAM_EVERY
            try:
                r = await c.get("https://api.alerts.in.ua/v1/alerts/active.json",
                                headers={"Authorization": "Bearer " + ALERTS_TOKEN})
                if r.status_code == 429:
                    wait = 30
                r.raise_for_status()
                act = {}
                for a in r.json().get("alerts", []):
                    o = a.get("location_oblast")
                    if a.get("alert_type") == "air_raid" and o in STEMS:
                        st = a.get("started_at", "")
                        act[o] = min(act.get(o, st), st)
                S["today"] += len([o for o in act if o not in S["act"]])
                S["act"], S["ts"] = act, time.time()
            except Exception as e:
                print("alerts.in.ua:", e)
            await asyncio.sleep(wait)


async def tg_listen():
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    while True:
        client = None
        try:
            client = TelegramClient(StringSession(TG_SESSION), TG_API_ID, TG_API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                print("TG_SESSION недійсна - Telegram вимкнено")
                return

            @client.on(events.NewMessage(chats=TG_CHANNELS))
            async def _(e):
                t = (e.raw_text or "").lower()
                if THREAT.search(t):
                    for reg, st in STEMS.items():
                        if re.search(st, t):
                            S["warn"][reg] = time.time() + WARN_TTL

            while client.is_connected():
                S["tg_ts"] = time.time()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("telegram:", e)
        finally:
            if client:
                await client.disconnect()
        await asyncio.sleep(15)


def status():
    now = time.time()
    if S["day"] != dt.date.today():
        S["day"], S["today"] = dt.date.today(), 0
    fresh = now - S["ts"] < STALE_AFTER
    out = {}
    for r in REGIONS:
        if fresh and r in S["act"]:
            out[r] = {"state": "alert", "since": S["act"][r]}
        elif S["warn"].get(r, 0) > now:
            out[r] = {"state": "warn"}
        elif fresh:
            out[r] = {"state": "calm"}      # "тиша" ТІЛЬКИ за свіжими даними
        else:
            out[r] = {"state": "unk"}
    out["_sources"] = {"alerts_in_ua": fresh, "telegram": now - S["tg_ts"] < STALE_AFTER}
    out["_today"] = S["today"]
    return out


@asynccontextmanager
async def lifespan(app):
    tasks = [asyncio.create_task(poll_alerts())]
    if TG_API_ID and TG_API_HASH and TG_SESSION:
        tasks.append(asyncio.create_task(tg_listen()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
NOCACHE = {"Cache-Control": "no-store"}


@app.get("/")
def read_root():
    return FileResponse(os.path.join(BASE, "index.html"), headers=NOCACHE)


@app.get("/settlements.json")
def settlements():
    p = os.path.join(BASE, "settlements.json")
    return FileResponse(p, headers=NOCACHE) if os.path.exists(p) else JSONResponse({}, status_code=404)


@app.get("/api/status")
def get_live_status():
    return JSONResponse(status(), headers=NOCACHE)
