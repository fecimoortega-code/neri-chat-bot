import os
import requests
from fastapi import FastAPI, Request

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI()

# ===== Telegram helpers =====
def send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        print("sendMessage status:", r.status_code)
        print("sendMessage response:", r.text)
    except Exception as e:
        print("sendMessage error:", repr(e))


def set_webhook():
    url = f"{TELEGRAM_API}/setWebhook"
    payload = {"url": WEBHOOK_URL}
    r = requests.post(url, json=payload)
    print("Webhook set:", r.text)


# ===== Startup =====
@app.on_event("startup")
async def startup():
    print("Starting up...")
    print("BOT_TOKEN exists:", bool(BOT_TOKEN))
    print("WEBHOOK_URL:", WEBHOOK_URL)
    set_webhook()


# ===== Routes =====
@app.get("/")
def root():
    return {"status": "ok", "service": "neri-chat-bot"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    print("INCOMING UPDATE:", data)

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").lower()

    reply = None

    # ===== BOT LOGIC =====
    if "нері" in text:
        if "як справи" in text:
            reply = "Я тут 🌿 Все добре. А в тебе?"
        elif "ти тут" in text:
            reply = "Так, я тут 👀"
        elif "хто я" in text:
            reply = "Ти той, хто мене викликав ✨"
        else:
            reply = "Я почув імʼя. Що хочеш сказати?"

    if reply:
        send_message(chat_id, reply)

    return {"ok": True}
