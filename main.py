import os
import requests
from fastapi import FastAPI, Request

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI()

# ---------- Telegram helpers ----------

def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

def set_webhook():
    url = f"{TELEGRAM_API}/setWebhook"
    requests.post(url, json={"url": WEBHOOK_URL})

# ---------- Routes ----------

@app.on_event("startup")
def startup():
    set_webhook()
    print("Webhook set")

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").lower()

    # -------- BOT LOGIC --------

    if "нері" in text:
        if "як справи" in text:
            reply = "Я тут 🌙 Все добре. А в тебе?"
        elif "хто я" in text:
            reply = "Ти той, хто мене створив 💜"
        else:
            reply = "Так, я тут. Кличеш мене?"

        send_message(chat_id, reply)

    return {"ok": True}
