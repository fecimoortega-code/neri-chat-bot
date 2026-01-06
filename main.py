import os
import re
import httpx
from fastapi import FastAPI, Request

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in environment variables")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is missing in environment variables")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI()


async def tg_post(method: str, payload: dict):
    url = f"{TELEGRAM_API}/{method}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


async def send_message(chat_id: int, text: str, reply_to_message_id: int | None = None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    return await tg_post("sendMessage", payload)


async def set_webhook():
    # drop_pending_updates=True щоб після перезапуску не сипались старі апдейти
    return await tg_post("setWebhook", {"url": WEBHOOK_URL, "drop_pending_updates": True})


@app.on_event("startup")
async def startup():
    await set_webhook()
    print("Webhook set to:", WEBHOOK_URL)


@app.get("/")
async def root():
    return {"status": "ok"}


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def should_respond(text: str) -> bool:
    # реагуємо якщо людина звертається "Нері, ..."
    return text.startswith("нері") or text.startswith("neri")


def make_reply(text: str) -> str | None:
    t = normalize(text)

    # Привітання / small-talk
    if "як справи" in t or "як ти" in t:
        return "Я на звʼязку 😼 Як ти, Дейз?"
    if "хто я" in t:
        return "Ти Дейз. І ти зараз тестиш мене як бог 😎"
    if t in ("привіт", "хай", "хелло", "hello", "йо"):
        return "Хей! Я Нері 😺 Скажи: «Нері, як справи?» або «Нері, зіграємо?»"

    # “Ігри”
    if "зіграємо" in t or "гра" in t:
        return "Окей! Вибирай: 1) кубик 🎲 2) камінь-ножиці-папір ✂️📄🪨"
    if "кубик" in t or "🎲" in t:
        return "Кидаю кубик! Напиши «Нері, кинути»"
    if "кинути" in t:
        # простий “рандом” без бібліотек — через Telegram dice було б краще,
        # але для тексту зробимо швидко:
        import random
        return f"Випало: {random.randint(1, 6)} 🎲"

    if "камінь" in t or "ножиці" in t or "папір" in t:
        return "Пиши: «Нері, камінь» або «Нері, ножиці» або «Нері, папір»"
    if t.endswith("камінь") or t.endswith("ножиці") or t.endswith("папір"):
        import random
        user = t.split()[-1]
        bot = random.choice(["камінь", "ножиці", "папір"])
        if user == bot:
            return f"Я: {bot}. Нічия 😼"
        wins = {("камінь", "ножиці"), ("ножиці", "папір"), ("папір", "камінь")}
        if (user, bot) in wins:
            return f"Я: {bot}. Ти виграв 💥"
        return f"Я: {bot}. Я виграв 😈"

    # Якщо звернулися “Нері, …” але не впізнали — відповідаємо все одно
    if should_respond(t):
        return "Я Нері 😺 Спробуй: «Нері, як справи?», «Нері, хто я?», «Нері, зіграємо?»"

    return None


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")
    msg_id = message.get("message_id")

    if not chat_id or not text:
        return {"ok": True}

    reply = make_reply(text)
    if reply:
        await send_message(chat_id, reply, reply_to_message_id=msg_id)

    return {"ok": True}
