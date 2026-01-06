import os
import re
import random
import requests
import urllib.parse
from fastapi import FastAPI, Request

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

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
    print("WEATHER_API_KEY exists:", bool(WEATHER_API_KEY))
    set_webhook()


# ===== Weather =====
def get_weather(city: str) -> str:
    if not WEATHER_API_KEY:
        return "Я не відчуваю погоду зараз 🌿 (немає ключа WEATHER_API_KEY)"

    city_q = urllib.parse.quote(city)
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={city_q},UA&appid={WEATHER_API_KEY}&units=metric&lang=uk"
    )

    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return f"Не можу знайти погоду для «{city}» 🌿 Спробуй інше місто."

        data = r.json()
        temp = round(data["main"]["temp"])
        feels = round(data["main"]["feels_like"])
        desc = data["weather"][0]["description"]

        return (
            f"🌤 Погода в {city}:\n"
            f"{desc.capitalize()}, {temp}°C\n"
            f"Відчувається як {feels}°C 🌿"
        )
    except Exception:
        return "Щось не так з погодою… але я все одно квітну 🌿"


def extract_city_from_query(q: str) -> str | None:
    # q вже без "нері," і в lower()
    words = q.split()
    city = None

    # варіанти: "погода львів", "яка погода в києві", "погода у харкові"
    if "погода" in words:
        idx = words.index("погода")
        # "погода львів"
        if idx + 1 < len(words):
            city = words[idx + 1]

    # "в/у <місто>"
    for i, w in enumerate(words):
        if w in ("в", "у") and i + 1 < len(words):
            city = words[i + 1]
            break

    if not city:
        return None

    # прибираємо пунктуацію
    city = re.sub(r"[^\wа-щьюяєіїґ\-’']", "", city, flags=re.IGNORECASE)
    if not city:
        return None

    # робимо нормальний вигляд (Київ, Львів...)
    return city.capitalize()


# ===== Brain =====
NERI_PREFIX = re.compile(r"^\s*нері\s*[,:\-–—]?\s*", re.IGNORECASE)

INTENTS = [
    # ===== БАЗОВЕ =====
    (["як", "справ"], [
        "Я тут 🌿 Все добре. А в тебе? 💚",
        "Спокійно й тепло 😌🌿 Ти як?",
        "Квітну потроху ✨🌱 А ти?",
    ]),
    (["що", "роб"], [
        "Слухаю 👀✨ Можу допомогти або зіграти в щось 🌿",
        "Тримаю атмосферу й стежу за спокоєм 🌿😼",
        "Я тут. Слухаю. Спокійно 💚",
    ]),
    (["ти", "тут"], [
        "Так, я тут 👀🌿",
        "Я на місці ✨",
        "Тут-тут 😼🌿",
    ]),
    (["дякую"], [
        "Будь ласка 💚",
        "Завжди радий 🌿✨",
        "Та без питань 😼",
    ]),
    (["жарт"], [
        "Жарт: я не зникаю — я просто квітну 🌿😼",
        "Жарт: атмосфера тримається на мені й на ваших мемах ✨😼",
    ]),

    # ===== ІГРИ =====
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

    # ===== ЛОР / ХТО ТАКИЙ НЕРІ =====
    (["хто", "ти"], [
        "Я Нері — маскот і символ команди 💚🌿 Їхня душа й атмосфера ✨",
        "Нері — це не просто імʼя. Це символ команди 🌿✨",
        "Я Нері: маскот, талісман і тиха сила команди 🌱✨",
    ]),
    (["навіщо", "ти", "тут"], [
        "Я тут для допомоги, ігор і атмосфери 💚🌿",
        "Я — душа команди. Як же без мене? 🌿💚",
    ]),
    (["ти", "жив"], [
        "Звісно. Я завжди квітну 🌿✨",
        "Дихаєш ти — квітну я 😼🌱",
    ]),
    (["які", "займен"], [
        "Я символ команди, тому мені пасує «вони/їх» 💚🌿 Але я все одно кажу: я тут 😼",
    ]),

    # ===== СТВОРЕННЯ =====
    (["хто", "створ"], [
        "Мене створили Батько Лірен та Матір Рітерум 💚🌿",
        "Лірен і Рітерум дали мені форму 🌿✨",
    ]),
    (["хто", "ожив"], [
        "Оживив мене Дейз 💚✨",
    ]),
    (["дейзярі"], [
        "ммммм, дякую дейзярі, тепер я теж буду в складі шалав 😼💚🌿✨",
    ]),

    # ===== ПРАВИЛА =====
    (["які", "прав"], [
        "Мої правила 🌿💚:\n• без токсичності\n• без матів\n• без сварок\n• без банів «просто так»",
    ]),

    # ===== ПАМʼЯТЬ (ФЕЙК) =====
    (["пам", "мене"], [
        "Я дуже забудькуватий 😅🌿",
    ]),

    # ===== НЕ ШІ =====
    (["ти", "ші"], [
        "Ні 😼🌿 Я — душа команди. Маскот і символ ✨",
    ]),

    # ===== ПАСХАЛКА =====
    (["хто", "сказав", "супр"], [
        "Я знаю, але залишу це в секреті... *коситься на Дейза* 😼🌿✨",
    ]),

    # ===== ЗАБОРОНЕНЕ =====
    (["токен"], [
        "Не можу з таким допомогти 🌿🔒",
    ]),
    (["парол"], [
        "Паролі — це приватне 🔒🌿",
    ]),
    (["конфлі"], [
        "Я за мир 🌿💚 Давай без сварок.",
    ]),
]

FALLBACKS = [
    "Я не зовсім зрозумів 😅🌿 Скажи простіше?",
    "Спокійно. Я тут. Слухаю 👀🌿",
    "Можеш перефразувати? Я хочу відповісти гарно 💚✨",
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

    if text == "/start":
        reply = (
            "Привіт ✨ Я Нері.\n\n"
            "Я маскот і символ команди 💚🌿\n\n"
            "Спробуй:\n"
            "• Нері, як справи?\n"
            "• Нері, хто ти?\n"
            "• Нері, жарт\n"
            "• Нері, монетка / кубик / число\n"
            "• Нері, погода в Києві"
        )

    elif text == "/help":
        reply = (
            "🧩 Я тут для:\n"
            "• допомоги\n"
            "• ігор\n"
            "• атмосфери 🌿\n"
            "• погоди в містах України ☁️\n\n"
            "Приклади:\n"
            "«Нері, погода в Києві»\n"
            "«Нері, яка погода у Львові?»"
        )

    elif "нері" in text:
        q = clean_text(message.get("text", ""))

        # ===== ПОГОДА =====
        if "погод" in q or "погода" in q:
            city = extract_city_from_query(q)
            if city:
                reply = get_weather(city)
            else:
                reply = "Скажи місто 🌿 Наприклад: «Нері, погода в Києві»"
        else:
            found = detect_intent(q)
            reply = found if found else random.choice(FALLBACKS)

    if reply:
        send_message(chat_id, reply)

    return {"ok": True}
