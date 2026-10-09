import os
import re
import asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, events

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

ALL_CHANNELS = [
    'vanek_nikolaev', 'monitor_radar', 'war_monitor', 
    'kpszs', 'dtek_ua', 'ukrenergo_official', 'kharkivoblenergo'
]

EXCLUDE_WORDS = ['куплю', 'продам', 'робота', 'вакансія', 'реклама', 'підписуйтесь']

# ДЕТАЛЬНІ ДАНІ ПО СВІТЛУ ТА АДРЕСАХ (ПЕРШОДЖЕРЕЛА)
live_state = {
    "locations": {
        "kharkiv": { 
            "title": "Харківська область / Харків", 
            "code": "green", "codeText": "ТИША", 
            "air_detail": "Повітряний простір контролюється.", 
            "outages_status": "Діють погодинні графіки відключень",
            "streets": ["Центр", "Салтівка", "Олексіївка", "Холодна Гора"]
        },
        "lozova": { 
            "title": "Лозова та Лозівська громада", 
            "code": "green", "codeText": "ТИША", 
            "air_detail": "Штатний режим погрози з повітря відсутні.", 
            "outages_status": "Без відключень (станом на 09.10.2026)",
            "streets": [
                "4-й мікрорайон (4 МКРН)", 
                "1-й мікрорайон", 
                "3-й мікрорайон", 
                "мікрорайон Південний", 
                "вул. Лозовського", 
                "вул. Соборна", 
                "Центр"
            ]
        },
        "kyiv": { 
            "title": "Київ та область", 
            "code": "green", "codeText": "ТИША", 
            "air_detail": "Небо чисте.", 
            "outages_status": "ДТЕК: стабілізаційні обмеження за графіком",
            "streets": ["Хрещатик", "Печерськ", "Подол", "Оболонь"]
        }
    },
    "radar": []
}

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/live-status")
async def get_status():
    return live_state

client = TelegramClient('varta_ukraine_session_v3', API_ID, API_HASH)

@client.on(events.NewMessage(chats=ALL_CHANNELS))
async def handle_incoming_feed(event):
    text = event.raw_text.lower()
    channel_username = getattr(event.chat, 'username', 'channel')

    if any(bad in text for bad in EXCLUDE_WORDS):
        return

    clean_text = event.raw_text.strip()
    is_outage_news = any(w in text for w in ['світл', 'відключ', 'графік', 'обленерго', 'укренерго', 'обмежен'])
    
    code = "green"
    code_text = "ТИША"
    cls = "code-green-tag"

    if not is_outage_news:
        if any(w in text for w in ['ракет', 'балістик', 'шахед', 'бпла', 'дрон', 'увага', 'зліт міг']):
            code = "red"
            code_text = "ТРЕВОГА"
            cls = "code-red-tag"

    target_key = "lozova" if ('лозов' in text or 'харків' in text) else ("kyiv" if 'київ' in text else None)

    if target_key and target_key in live_state["locations"]:
        if is_outage_news:
            live_state["locations"][target_key]["outages_status"] = f"[@{channel_username}]: {clean_text[:140]}..."
        else:
            if code != "green":
                live_state["locations"][target_key]["code"] = code
                live_state["locations"][target_key]["codeText"] = code_text
                live_state["locations"][target_key]["air_detail"] = f"[@{channel_username}]: {clean_text[:140]}..."

    if not is_outage_news and code != "green":
        live_state["radar"].insert(0, {
            "title": f"📍 Загроза",
            "route": clean_text[:120] + "...",
            "tag": code_text,
            "cls": cls
        })
        live_state["radar"] = live_state["radar"][:10]

async def start_telegram():
    if API_ID and API_HASH:
        await client.start()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_telegram())

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
