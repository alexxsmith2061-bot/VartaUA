import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
from telegram import Bot

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Токен бота та ID каналів, які потрібно моніторити
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Тимчасове сховище статусів тривог по регіонах/містах
alerts_database = {}

class AlertUpdate(BaseModel):
    region: str
    status: bool

@app.get("/")
def read_root():
    return {"status": "online", "message": "Air Alert Dashboard API is running with Telegram Bot"}

@app.get("/api/alerts")
def get_alerts():
    return alerts_database

@app.post("/api/update-alert")
def update_alert(update: AlertUpdate):
    alerts_database[update.region] = update.status
    return {"success": True, "region": update.region, "status": update.status}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
