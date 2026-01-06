import os
import re
import random
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
    payload = {"chat_id": chat_id, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print("sendMessage status:", r.status_code)
        print("sendMessage response:", r.text)
    except Exception as e:
        print("sendMessage error:", repr(e))


def set_webhook():
    url = f"{TELEGRAM_API}/setWebhook"
    payload = {"url": WEBHOOK_URL, "drop_pending_updates": True}
    r = requests.post(url, json=payload)
    print("Webhook set:", r.text)


# ===== Startup =====
@app.on_event("startup")
async def startup():
    print("Starting up...")
    print("BOT_TOKEN exists:", bool(BOT_TOKEN))
    print("WEBHOOK_URL:", WEBHOOK_URL)
    set_webhook()


# ===== Brain =====
NERI_PREFIX = re.compile(r"^\s*нері\s*[,:\-–—]?\s*", re.IGNORECASE)

INTENTS = [
    (["як", "справ"], [
        "Я тут 🌿 Все добре. А в тебе?",
        "Почуваюсь спокійно 😌 А ти як?",
        "Все нормально, дякую що питаєш 💚",
    ]),
    (["що", "роб"], [
        "Сиджу тут і слухаю тебе 👀",
        "Слідкую за чатом і несу спокій ✨",
        "Чекаю твого повідомлення 😼",
    ]),
    (["ти", "тут"], [
        "Так, я тут 👋",
        "Я нікуди не зник 🌙",
        "Я з тобою 🙂",
    ]),
    (["хто", "я"], [
        "Ти той, хто мене покликав ✨",
        "Ти важлива частина цього чату 💚",
    ]),
    (["дякую"], [
        "Будь ласка 🙂",
        "Завжди радий допомогти 💫",
        "Нема за що 😌",
    ]),
    (["жарт"], [
        "Жарт: я бот, але з душею 😅",
        "Жарт: я не втомлююсь, я просто оновлююсь 😴",
    ]),
    (["монет"], [
        "🪙 Орел",
        "🪙 Решка",
    ]),
    (["куб"], [
        lambda: f"🎲 Випало: {random.randint(1, 6)}",
    ]),
    (["числ"], [
        lambda: f"🔢 Моє число: {random.randint(1, 100)}",
    ]),
    (["сумно"], [
        "Я тут поруч 💚 Хочеш поговорити?",
        "Можеш трохи видихнути. Я з тобою 🌿",
    ]),
    (["рад"], [
        "Це чудово 😄 Мені приємно це чути!",
        "Радий разом з тобою ✨",
    ]),
]

FALLBACKS = [
    "Я не зовсім зрозумів 😅 Спробуй сказати інакше?",
    "Можеш трохи уточнити? Я хочу відповісти добре 💚",
    "Я слухаю, просто скажи простіше 🙂",
]

def clean_text(text: str) -> str:
    t = text.strip()
    t = NERI_PREFIX.sub("", t)
    t = re.sub(r"\s+", " ", t)
    return t.lower()

def pick_response(options):
    choice = random.choice(options)
    return choice() if callable(choice) else choice

def detect_intent(query: str):
    for keywords, responses in INTENTS:
        if all(k in query for k in keywords):
            return pick_response(responses)
    return None


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

    # ===== COMMANDS =====
    if text == "/start":
        reply = (
            "Привіт ✨ Я Нері.\n\n"
            "Мене можна кликати так:\n"
            "• Нері, як справи?\n"
            "• Нері, що робиш?\n"
            "• Нері, жарт\n"
            "• Нері, монетка / кубик / число\n\n"
            "Я тут, якщо ти захочеш поговорити 💚"
        )

    elif text == "/help":
        reply = (
            "🧩 Я вмію:\n"
            "• відповідати на питання\n"
            "• трохи жартувати\n"
            "• гратись з рандомом\n\n"
            "Просто напиши:\n"
            "«Нері, як справи?»"
        )

    # ===== NAME CALL =====
    elif "нері" in text:
        q = clean_text(message.get("text", ""))
        found = detect_intent(q)
        reply = found if found else random.choice(FALLBACKS)

    if reply:
        send_message(chat_id, reply)

    return {"ok": True}
