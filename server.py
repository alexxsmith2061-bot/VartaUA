import os
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Кеш даних про тривоги по всій Україні
alerts_cache = {}

async def fetch_ukraine_alerts():
    """Автоматично тягне дані про тривоги по всіх регіонах/містах"""
    global alerts_cache
    async with httpx.AsyncClient() as client:
        try:
            # Офіційне безкоштовне джерело статусів тривог
            response = await client.get("https://api.alerts.in.ua/v1/alerts/active.json", timeout=10)
            if response.status_code == 200:
                alerts_cache = response.json()
        except Exception as e:
            print(f"Помилка оновлення даних: {e}")

@app.on_event("startup")
async def schedule_alert_updates():
    """Запускає фонове оновлення даних кожні 15 секунд"""
    async def loop():
        while True:
            await fetch_ukraine_alerts()
            await asyncio.sleep(15)
    asyncio.create_task(loop())

@app.get("/")
def read_root():
    return {
        "status": "online",
        "bot_configured": bool(BOT_TOKEN),
        "message": "Система моніторингу тривог та відключень працює автоавтоматично"
    }

@app.get("/api/alerts")
def get_all_alerts():
    return alerts_cache

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
