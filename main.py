import os
import re
import random
import requests
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
CITY_ALIASES = {
    "києві": "київ", "києва": "київ", "київ": "київ",
    "львові": "львів", "львова": "львів", "львів": "львів",
    "одесі": "одеса", "одеси": "одеса", "одеса": "одеса",
    "харкові": "харків", "харкова": "харків", "харків": "харків",
    "дніпрі": "дніпро", "дніпра": "дніпро", "дніпро": "дніпро",
    "запоріжжі": "запоріжжя", "запоріжжя": "запоріжжя",
}

# латинські варіанти для стабільного пошуку в OpenWeather
CITY_LATIN = {
    "київ": "Kyiv",
    "львів": "Lviv",
    "одеса": "Odesa",
    "харків": "Kharkiv",
    "дніпро": "Dnipro",
    "запоріжжя": "Zaporizhzhia",
}

WEATHER_STOPWORDS = {
    "погода", "яка", "яке", "який", "зараз", "сьогодні", "будь", "ласка",
    "покажи", "скажи", "напиши", "негайно", "будь-ласка", "пліз", "плиз",
    "у", "в", "на", "по", "для", "місті", "місто", "про",
    "нері"
}

def extract_city_from_query(q: str) -> str | None:
    # q вже без "нері," і в lower()
    s = re.sub(r"[^\w\s\-’ʼіїєґа-яА-Я]", " ", q, flags=re.UNICODE).strip().lower()
    parts = [p for p in s.split() if p and p not in WEATHER_STOPWORDS]
    if not parts:
        return None
    # якщо останні 2 слова схожі на назву (наприклад "івано франківськ")
    if len(parts) >= 2:
        last2 = " ".join(parts[-2:])
        if len(last2) >= 4:
            return last2
    return parts[-1]

def normalize_city(city: str) -> str:
    c = city.strip().lower()
    if c in CITY_ALIASES:
        return CITY_ALIASES[c]

    # легка евристика для відмінків
    for suffix, repl in [("ові", ""), ("еві", ""), ("і", "а"), ("у", "а"), ("ї", "я")]:
        if len(c) > 4 and c.endswith(suffix):
            guess = c[:-len(suffix)] + repl
            return CITY_ALIASES.get(guess, guess)

    return c

def weather_emoji(main: str) -> str:
    m = (main or "").lower()
    if "clear" in m:
        return "☀️"
    if "cloud" in m:
        return "☁️"
    if "rain" in m or "drizzle" in m:
        return "🌧️"
    if "thunder" in m:
        return "⛈️"
    if "snow" in m:
        return "❄️"
    if "mist" in m or "fog" in m or "haze" in m:
        return "🌫️"
    return "🌿"

def _geocode_candidates(city_norm: str) -> list[str]:
    lat = CITY_LATIN.get(city_norm)
    cands = []
    # 1) кирилиця з країною
    cands.append(f"{city_norm},UA")
    # 2) кирилиця без країни
    cands.append(city_norm)
    # 3-4) латиниця (якщо є)
    if lat:
        cands.append(f"{lat},UA")
        cands.append(lat)
    return cands

def _try_geocode(q: str):
    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {"q": q, "limit": 5, "appid": WEATHER_API_KEY}
    gr = requests.get(geo_url, params=params, timeout=10)
    print("GEOCODE TRY:", q, gr.status_code, gr.text)

    if gr.status_code != 200:
        return None

    arr = gr.json()
    if not arr:
        return None

    ua = [x for x in arr if x.get("country") == "UA"]
    return ua[0] if ua else arr[0]

def get_weather(city_raw: str) -> str:
    if not WEATHER_API_KEY:
        return "Я не відчуваю погоду зараз 🌿 (немає ключа WEATHER_API_KEY)"

    city_norm = normalize_city(city_raw)

    try:
        # --- Geocoding (кілька спроб) ---
        geo = None
        for cand in _geocode_candidates(city_norm):
            geo = _try_geocode(cand)
            if geo:
                break

        if not geo:
            return f"Не можу знайти погоду для «{city_raw}» 🌿 Спробуй інше місто."

        lat = geo["lat"]
        lon = geo["lon"]
        nice_name = (
            geo.get("local_names", {}).get("uk")
            or geo.get("name")
            or city_raw
        )

        # --- Current weather ---
        w_url = "https://api.openweathermap.org/data/2.5/weather"
        w_params = {
            "lat": lat,
            "lon": lon,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "uk",
        }
        wr = requests.get(w_url, params=w_params, timeout=10)
        print("WEATHER:", wr.status_code, wr.text)

        if wr.status_code != 200:
            return f"Щось не так з погодою для «{nice_name}» 🌿"

        w = wr.json()
        temp = round(w["main"]["temp"])
        feels = round(w["main"]["feels_like"])
        desc = w["weather"][0].get("description", "")
        main = w["weather"][0].get("main", "")
        em = weather_emoji(main)

        return f"{em} {nice_name}: {temp}°C (відчувається як {feels}°C), {desc} 🌿"

    except Exception as e:
        print("WEATHER ERROR:", repr(e))
        return "Я спіткнувся об хмаринку 🌿 Спробуй ще раз трохи пізніше."


# ===== Brain =====
NERI_PREFIX = re.compile(r"^\s*нері\s*[,:\-–—]?\s*", re.IGNORECASE)

INTENTS = [
    # ===== БАЗОВЕ =====
    (["привіт"], [
        "Привіт 💚🌿 Я тут. Слухаю 👀✨",
        "О, привіт 😼🌿 Як твій день?",
        "Привіт-привіт ✨🌱 Я вже квітну, а ти?",
    ]),
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
            "• Нері, привіт\n"
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
            "«Нері, привіт»\n"
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
