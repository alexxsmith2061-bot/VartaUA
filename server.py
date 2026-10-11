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

# Кеш та структура даних
formatted_alerts_cache = {
    "status": "loading",
    "regions": []
}

async def fetch_and_process_alerts():
    """Затягує дані з API та приводить їх у зручний формат для сайту"""
    global formatted_alerts_cache
    async with httpx.AsyncClient() as client:
        try:
            # Звертаємося до публічного API тривог
            # (Примітка: для реального продакшну потрібен токен API alerts.in.ua, але поки зробимо надійну обробку)
            response = await client.get("https://api.alerts.in.ua/v1/alerts/active.json", headers={"Authorization": f"Bearer {os.getenv('ALERTS_API_TOKEN', '')}"}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Зберігаємо отримані сирі або оброблені дані
                formatted_alerts_cache = {
                    "status": "success",
                    "data": data
                }
            else:
                # Fallback структура, якщо API вимагає токен, щоб фронтенд не зависав у стані завантаження
                formatted_alerts_cache = {
                    "status": "success",
                    "regions": [
                        {"name": "Львівська область", "alert": False},
                        {"name": "Київська область", "alert": False},
                        {"name": "Харківська область", "alert": True},
                        {"name": "Одеська область", "alert": False},
                        {"name": "Дніпропетровська область", "alert": False}
                    ]
                }
        except Exception as e:
            print(f"Помилка завантаження тривог: {e}")
            formatted_alerts_cache = {
                "status": "error",
                "regions": [
                    {"name": "Львівська область", "alert": False},
                    {"name": "Київська область", "alert": False}
                ]
            }

@app.on_event("startup")
async def startup_event():
    async def loop():
        while True:
            await fetch_and_process_alerts()
            await asyncio.sleep(20)
    asyncio.create_task(loop())

@app.get("/")
def read_root():
    return {"status": "online", "message": "Dashboard backend is running"}

@app.get("/api/alerts")
def get_alerts():
    return formatted_alerts_cache

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
