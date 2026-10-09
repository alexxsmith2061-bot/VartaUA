import os
import re
import asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, events

# ТЕЛЕГРАМ API
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")

# ОФІЦІЙНІ ТА МОНІТОРИНГОВІ КАНАЛИ (ВІЙСЬКОВА БЕЗПЕКА + ЕНЕРГЕТИКА)
ALL_CHANNELS = [
    'vanek_nikolaev', 'monitor_radar', 'war_monitor', 
    'kpszs', 'dtek_ua', 'ukrenergo_official', 'kharkivoblenergo'
]

EXCLUDE_WORDS = ['куплю', 'продам', 'робота', 'вакансія', 'реклама', 'підписуйтесь']

# СТРУКТУРА ДЛЯ ВСІХ РЕГІОНІВ ТА ОФІЦІЙНИХ ДАНИХ ПРО СВІТЛО
live_state = {
    "locations": {
        "lozova": { "title": "📍 Лозова / Харківщина", "code": "green", "codeText": "ТИША", "detail": "Моніторинг регіону активний...", "outages": "⚪ Очікування даних від Харківобленерго" },
        "kyiv": { "title": "📍 Київ та область", "code": "green", "codeText": "ТИША", "detail": "Штатний режим.", "outages": "⚪ Очікування даних від ДТЕК" },
        "dnipro": { "title": "📍 Дніпро / Запоріжжя", "code": "green", "codeText": "ТИША", "detail": "Штатний режим.", "outages": "⚪ Штатний режим" },
        "odesa": { "title": "📍 Одеса та область", "code": "green", "codeText": "ТИША", "detail": "Штатний режим.", "outages": "⚪ Штатний режим" },
        "lviv": { "title": "📍 Львів / Захід", "code": "green", "codeText": "ТИША", "detail": "Штатний режим.", "outages": "⚪ Штатний режим" },
        "kharkiv": { "title": "📍 Харків", "code": "green", "codeText": "ТИША", "detail": "Моніторинг небезпеки...", "outages": "⚪ Екстрені / аварійні" }
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

client = TelegramClient('varta_ukraine_session', API_ID, API_HASH)

@client.on(events.NewMessage(chats=ALL_CHANNELS))
async def handle_incoming_feed(event):
    text = event.raw_text.lower()
    channel_username = getattr(event.chat, 'username', 'channel')

    if any(bad in text for bad in EXCLUDE_WORDS):
        return

    clean_text = event.raw_text.strip()
    
    # 1. Обробка тривог та військових загроз
    code = "green"
    code_text = "ТИША"
    cls = "code-green-tag"

    if any(w in text for w in ['ракет', 'балістик', 'шахед', 'увага', 'зліт міг']):
        code = "red"
        code_text = "ТРИВОГА"
        cls = "code-red-tag"
    elif any(w in text for w in ['активність', 'розвідка', 'нвру', 'курсу']):
        code = "yellow"
        code_text = "УВАГА"
        cls = "code-yellow-tag"

    # 2. Обробка інформації про світло / графіки відключень
    outages_info = None
    if any(w in text for w in ['світл', 'відключ', 'графік', 'обленерго', 'укренерго', 'обмежен']):
        if any(w in text for w in ['скасов', 'не діють', 'відмінили', 'без відключень', 'розпорядження скасовано']):
            outages_info = "🟢 Графіки скасовані / світло є"
        elif any(w in text for w in ['екстрені', 'аварійні', 'погодинні', 'обмеження']):
            outages_info = clean_text[:110] + "..."
        else:
            outages_info = clean_text[:110] + "..."

    # Розподіляємо по регіонах
    target_key = "lozova"
    if any(w in text for w in ['київ', 'київськ', 'dtek']): target_key = "kyiv"
    elif any(w in text for w in ['дніпр', 'запоріж']): target_key = "dnipro"
    elif any(w in text for w in ['одес']): target_key = "odesa"
    elif any(w in text for w in ['львів']): target_key = "lviv"
    elif any(w in text for w in ['харків', 'харківськ', 'обленерго']): target_key = "kharkiv"

    # Якщо новина загальноукраїнська від Укренерго — оновлюємо статус для всіх регіонів або для головного
    if 'укренерго' in channel_username or 'укренерго' in text:
        for k in live_state["locations"]:
            if outages_info:
                live_state["locations"][k]["outages"] = outages_info

    # Оновлюємо конкретний регіон
    if target_key in live_state["locations"]:
        if code != "green":
            live_state["locations"][target_key]["code"] = code
            live_state["locations"][target_key]["codeText"] = code_text
            live_state["locations"][target_key]["detail"] = f"[@{channel_username}]: {clean_text[:150]}..."
        
        if outages_info:
            live_state["locations"][target_key]["outages"] = outages_info

    # Загальний радар загроз
    if code != "green":
        live_state["radar"].insert(0, {
            "title": f"📍 Регіон: {target_key.upper()} (@{channel_username})",
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
