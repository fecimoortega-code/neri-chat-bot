import os
import re
import random
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")  # можна пусто
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")        # напр: https://твій-сервіс.onrender.com/webhook

TG_API = "https://api.telegram.org"

# ---------- helpers ----------
async def tg_send_message(chat_id: int, text: str, reply_to_message_id: int | None = None):
    if not BOT_TOKEN:
        # якщо токен не заданий — просто не шлемо
        return

    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(f"{TG_API}/bot{BOT_TOKEN}/sendMessage", json=payload)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_neri_call(text: str) -> bool:
    # реагуємо коли починається з "Нері" / "Neri"
    t = (text or "").strip().lower()
    return t.startswith("нері") or t.startswith("neri")


def strip_neri_prefix(text: str) -> str:
    # "Нері, як справи" -> "як справи"
    t = normalize(text)
    t = re.sub(r"^(нері|neri)\s*[,!:–—-]?\s*", "", t, flags=re.IGNORECASE)
    return t.strip()


def answer(user_first_name: str, user_id: int, msg: str) -> str:
    raw = normalize(msg)
    if not raw:
        return "Я тут 🙂 Напиши: «Нері, як справи?» або «Нері, допомога»."

    if not is_neri_call(raw):
        # можна зробити щоб реагував тільки на згадку. Зараз — тільки якщо починається з Нері.
        return ""

    q = strip_neri_prefix(raw).lower()

    # help
    if q in ("допомога", "help", "команди", "що ти вмієш", "шо ти вмієш"):
        return (
            "Я Нері 🤖\n"
            "Команди:\n"
            "• Нері, як справи?\n"
            "• Нері, хто я?\n"
            "• Нері, монетка\n"
            "• Нері, кубик\n"
            "• Нері, число\n"
            "• Нері, анекдот (простенький)\n"
        )

    # small talk
    if "як справ" in q or q in ("як ти", "як справи"):
        return "Нормально 😎 Працюю на вебхуку. А в тебе як?"

    if "хто я" in q:
        return f"Ти — {user_first_name} (id: {user_id}). І ти дуже підозріло крутий 😼"

    # games
    if "монет" in q or "coin" in q:
        return "🪙 " + random.choice(["Орел", "Решка"])

    if "куб" in q or "dice" in q:
        return "🎲 Випало: " + str(random.randint(1, 6))

    if "числ" in q or "number" in q:
        return "🔢 Моє число: " + str(random.randint(1, 100))

    # silly
    if "анекд" in q or "жарт" in q:
        return "Короткий жарт: програміст не спить — він компілюється 😴💻"

    # fallback
    return "Я не до кінця зрозумів 😅 Напиши «Нері, допомога»."


# ---------- health endpoints ----------
@app.get("/")
def root():
    return {"status": "ok", "service": "neri-chat-bot"}

@app.get("/ping")
def ping():
    return {"ping": "pong"}


# ---------- webhook ----------
@app.post("/webhook")
async def webhook(request: Request):
    # optional: простий секрет у заголовку
    if WEBHOOK_SECRET:
        got = request.headers.get("X-Webhook-Secret", "")
        if got != WEBHOOK_SECRET:
            return {"ok": False, "error": "bad secret"}

    update = await request.json()

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or ""
    msg_id = message.get("message_id")

    user = message.get("from") or {}
    first_name = user.get("first_name") or "друже"
    user_id = user.get("id") or 0

    resp = answer(first_name, user_id, text)
    if resp:
        await tg_send_message(chat_id, resp, reply_to_message_id=msg_id)

    return {"ok": True}


# ---------- set webhook on startup (optional) ----------
@app.on_event("startup")
async def on_startup():
    # якщо в Render додаси WEBHOOK_URL, бот сам спробує підключити вебхук
    if not BOT_TOKEN or not WEBHOOK_URL:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(
            f"{TG_API}/bot{BOT_TOKEN}/setWebhook",
            json={"url": WEBHOOK_URL, "drop_pending_updates": True},
        )
