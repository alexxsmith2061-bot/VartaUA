import os
import re
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, events

# ТЕЛЕГРАМ API (Береться автоматично з налаштувань Render)
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

# БІЛИЙ СПИСОК КАНАЛІВ МОНІТОРИНГУ
OFFICIAL_CHANNELS = ['kpszs', 'synegubov', 'kharkivoda']
RADAR_CHANNELS = ['vanek_nikolaev', 'radar_raket', 'monitorkarta']
LOCAL_CHANNELS = ['lozo_va', 'lozovaya_live', 'izium_live', 'barvinkove_news']
ALL_CHANNELS = OFFICIAL_CHANNELS + RADAR_CHANNELS + LOCAL_CHANNELS

LOCATIONS = {
    'lozova': ['лозов', 'лозовая', 'авіловка', 'панютине'],
    'blyzniuky': ['близнюк', 'близнюки'],
    'barvinkove': ['барвінк', 'барвенково'],
    'izium': ['ізюм', 'изюм']
}

EXCLUDE_WORDS = ['куплю', 'продам', 'робота', 'вакансія', 'реклама', 'підписуйтесь']
msg_history = []

live_state = {
    "locations": {
        "lozova": {"title": "📍 Лозівська громада / Лозова", "code": "green", "codeText": "ТИША", "detail": "🟢 У повітряному просторі чисто. Моніторимо джерела."},
        "blyzniuky": {"title": "📍 Близнюківська громада", "code": "green", "codeText": "ТИША", "detail": "🟢 Загрози не зафіксовано."},
        "barvinkove": {"title": "📍 Барвінківська громада", "code": "green", "codeText": "ТИША", "detail": "🟢 Спокійно."},
        "izium": {"title": "📍 Ізюмський район", "code": "green", "codeText": "ТИША", "detail": "🟢 Штатна ситуація."}
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

client = TelegramClient('varta_render_session', API_ID, API_HASH)

def cross_validate_event(loc_key, raw_text, channel_username):
    now = datetime.now()
    global msg_history
    msg_history = [m for m in msg_history if now - m['time'] < timedelta(minutes=10)]
    msg_history.append({'channel': channel_username, 'loc': loc_key, 'text': raw_text.lower(), 'time': now})

    matched_sources = set([m['channel'] for m in msg_history if m['loc'] == loc_key])
    has_official = any(ch in OFFICIAL_CHANNELS or ch in RADAR_CHANNELS for ch in matched_sources)

    if len(matched_sources) >= 2 or has_official:
        return "red", "КОД ЧЕРВОНИЙ"
    else:
        return "yellow", "КОД ЖОВТИЙ"

@client.on(events.NewMessage(chats=ALL_CHANNELS))
async def handle_incoming_feed(event):
    text = event.raw_text.lower()
    channel_username = getattr(event.chat, 'username', 'channel')

    if any(bad in text for bad in EXCLUDE_WORDS):
        return

    for loc_key, keywords in LOCATIONS.items():
        if any(kw in text for kw in keywords):
            clean_text = event.raw_text.strip()
            code, code_text = cross_validate_event(loc_key, clean_text, channel_username)

            live_state["locations"][loc_key] = {
                "title": live_state["locations"][loc_key]["title"],
                "code": code,
                "codeText": code_text,
                "detail": f"📡 <b>[{channel_username}]</b>: {clean_text}"
            }

            live_state["radar"].insert(0, {
                "title": f"📍 Зведення: {loc_key.upper()}",
                "route": clean_text[:90] + "...",
                "tag": code_text,
                "cls": "code-red-tag" if code == "red" else "code-yellow-tag"
            })
            live_state["radar"] = live_state["radar"][:6]

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
