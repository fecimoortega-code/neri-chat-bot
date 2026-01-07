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
    s = re.sub(r"[^\w\s\-’ʼіїєґа-яА-Я]", " ", q, flags=re.UNICODE).strip().lower()
    parts = [p for p in s.split() if p and p not in WEATHER_STOPWORDS]
    if not parts:
        return None
    if len(parts) >= 2:
        last2 = " ".join(parts[-2:])
        if len(last2) >= 4:
            return last2
    return parts[-1]

def normalize_city(city: str) -> str:
    c = city.strip().lower()
    if c in CITY_ALIASES:
        return CITY_ALIASES[c]

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
    cands = [f"{city_norm},UA", city_norm]
    if lat:
        cands += [f"{lat},UA", lat]
    return cands

def _try_geocode(q: str):
    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {"q": q, "limit": 5, "appid": WEATHER_API_KEY}
    gr = requests.get(geo_url, params=params, timeout=10)
    print("GEOCODE TRY:", q, gr.status_code)

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

        w_url = "https://api.openweathermap.org/data/2.5/weather"
        w_params = {
            "lat": lat,
            "lon": lon,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "uk",
        }
        wr = requests.get(w_url, params=w_params, timeout=10)
        print("WEATHER:", wr.status_code)

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

NATURE_EMOJIS = ["🌿", "🍃", "🌱", "🍀", "🪴", "🌸", "🌼", "✨", "👀", "😼"]
def n_emo():
    return random.choice(NATURE_EMOJIS)

# ===== Pronouns / gender enforcement (Нері: він/вони) =====
FEM_TO_MASC_REPLACEMENTS = [
    (r"\bя була\b", "я був"),
    (r"\bя зробила\b", "я зробив"),
    (r"\bя сказала\b", "я сказав"),
    (r"\bя відповіла\b", "я відповів"),
    (r"\bя хотіла\b", "я хотів"),
    (r"\bя могла\b", "я міг"),
    (r"\bя не могла\b", "я не міг"),
    (r"\bя забула\b", "я забув"),
    (r"\bя зрозуміла\b", "я зрозумів"),
    (r"\bя думала\b", "я думав"),
    (r"\bя бачила\b", "я бачив"),
    (r"\bя пішла\b", "я пішов"),
    (r"\bя прийшла\b", "я прийшов"),
    (r"\bя стала\b", "я став"),
]

def enforce_neri_pronouns(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    for pattern, repl in FEM_TO_MASC_REPLACEMENTS:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)
    return t

# ===== “екстравертність” (інколи капсом, але рідко) =====
def neri_style(text: str) -> str:
    if not text:
        return text

    t = text.strip()

    # 25% шанс зробити одне слово/фразу капсом
    if random.random() < 0.25:
        words = t.split()
        if len(words) >= 3:
            i = random.randint(0, len(words) - 1)
            words[i] = words[i].upper()
            t = " ".join(words)

    # додай емодзі інколи, без спаму
    if random.random() < 0.25 and len(t) < 260:
        if not t.endswith(("🌿","✨","💚","😼","👀","🍃","🌱","🍀","🪴","🌸","🌼")):
            t = t + " " + n_emo()

    # ВАЖЛИВО: фіксуємо рід/займенники
    t = enforce_neri_pronouns(t)
    return t

NERI_AGE = 2
NERI_BDAY = "16.09.2025"

# ===== Profiles (ХТО ТАКИЙ/ТАКА) =====
TEAM_PROFILES = {
    "nerineris": {
        "name": "Nerineris",
        "roles": "Найкраща пусічка у СВІТІ",
        "aka": ["nerineris", "нерінеріс", "нері"],
    },
    "riterum": {
        "name": "Riterum",
        "roles": "Лідер, вокал, переклад, SMM",
        "aka": ["riterum", "рітерум", "ритерум", "рітерума", "рум", "rum"],
    },
    "liren": {
        "name": "LiRen",
        "roles": "Лідер, вокал, ілюстрації, переклад",
        "aka": ["liren", "лірен", "лірена", "лірену"],
    },
    "daze": {  # ✅ правка: ключ daze
        "name": "Daze",
        "roles": "Адмін, відео",
        "aka": ["daze", "дейз", "deyz", "дейзик"],
    },
    "tori": {
        "name": "Tori_frr",
        "roles": "Адмін, вокал, переклад, ілюстрації, відео",
        "aka": ["tori_frr", "торі", "tori", "торіфрр", "tori-frr"],
    },
    "pina": {
        "name": "ПІНОПЛАСТІВОЧКА (Піна)",
        "roles": "Вокал, ілюстрації, переклад",
        "aka": ["пінопластівочка", "піна", "pinoplastivochka", "pina"],
    },
    "alyvian": {  # ✅ правка: alyvian
        "name": "Alyvian",
        "roles": "Вокал, гармонії",
        "aka": ["alyvian", "aluvian", "алувіан", "аливіан"],
    },
    "miraj": {
        "name": "Miraj",
        "roles": "Вокал, гармонії",
        "aka": ["miraj", "мірай", "міраж"],
    },
    "stellarskrim": {
        "name": "StellarSkriM",
        "roles": "Зведення",
        "aka": ["stellarskrim", "стеллар", "stellar", "stellarskrim3"],
    },
    "rybka": {
        "name": "Рибка",
        "roles": "Відео",
        "aka": ["рибка", "rybka"],
    },
    "lee": {
        "name": "Lee",
        "roles": "Ілюстрації",
        "aka": ["lee", "лі"],
    },
    "mokatroIa": {
        "name": "мокатролa",
        "roles": "Ілюстрації",
        "aka": ["мокатролa", "мокатроля", "mokatrola"],
    },
    "moka": {  # ✅ додано: Мока
        "name": "Moka",
        "roles": "Ілюстрації",
        "aka": ["moka", "мока"],
    },
    "inky": {
        "name": "InkyLove",
        "roles": "Вокал",
        "aka": ["inkylove", "інкі", "inky"],
    },
    "lesya": {
        "name": "Леся/moemoneya",
        "roles": "Ілюстрації",
        "aka": ["леся", "moemoneya", "lesya"],
    },
    "mari": {
        "name": "MARi",
        "roles": "Вокал, зведення, гармонії",
        "aka": ["mari", "марі"],
    },
    "dreamy": {
        "name": "Dreamy",
        "roles": "Ілюстрації",
        "aka": ["dreamy", "дрімі", "dream"],
    },
    "illya": {
        "name": "Ілля",
        "roles": "Зведення",
        "aka": ["ілля", "іллі", "іллю", "illya"],
    },
    "pechenig": {
        "name": "pechenig",
        "roles": "Ілюстрації, відео",
        "aka": ["pechenig", "печеніг"],
    },
    "zhuk": {
        "name": "Дмитро Жук",
        "roles": "Ілюстрації",
        "aka": ["жук", "дмитро жук", "zhuk", "duke_zhukem"],
    },
    "asareal": {
        "name": "Asareal",
        "roles": "Вокал, зведення",
        "aka": ["asareal", "асареал"],
    },
    "em": {
        "name": "E_M",
        "roles": "Зведення, інструментал",
        "aka": ["e_m", "e m", "ем", "em"],
    },
    "azri": {  # ✅ додано: Азрі
        "name": "Azri",
        "roles": "—",
        "aka": ["azri", "азрі", "azry"],
    },
}

def _norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("’", "'").replace("ʼ", "'")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\wа-щьюяєіїґ\-'\s]", "", s, flags=re.IGNORECASE)
    return s.strip()

def find_profile(name_raw: str):
    key = _norm_name(name_raw)
    if not key:
        return None

    # 1) exact alias match
    for _, p in TEAM_PROFILES.items():
        for a in p.get("aka", []):
            if _norm_name(a) == key:
                return p

    # 2) contains match (на випадок "хто така пінааа" або "tori_frr???")
    for _, p in TEAM_PROFILES.items():
        for a in p.get("aka", []):
            aa = _norm_name(a)
            if aa and (aa in key or key in aa):
                return p

    return None

FACT_QUERY_HINTS = [
    "хто такий", "хто така", "хто це", "що за", "розкажи про", "розкажи хто"
]

def extract_quoted_name(raw: str) -> str | None:
    m = re.search(r"[\"“”'‘’](.+?)[\"“”'‘’]", raw)
    return m.group(1).strip() if m else None

def answer_who_is(raw_text: str, q: str) -> str | None:
    if not any(h in q for h in FACT_QUERY_HINTS):
        return None

    name = extract_quoted_name(raw_text)
    if not name:
        parts = q.split()
        name = parts[-1] if parts else ""

    prof = find_profile(name)
    if not prof:
        return None

    name_out = prof.get("name", "Хтось")
    roles = prof.get("roles", "—")
    return neri_style(f"{name_out} — {roles} 🌿")


# політика/війна — табу
SERIOUS_KEYWORDS = ["політик", "вибор", "парті", "війна", "фронт", "зброя", "ракета"]
def is_serious_topic(q: str) -> bool:
    return any(k in q for k in SERIOUS_KEYWORDS)
def serious_refusal() -> str:
    return "Я не говорю про політику/війну 🌿 Давай краще про щось тепле й командне 💚"


# ===== Smalltalk (мільйон питань -> багато відповідей) =====
def _norm_ua(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("’", "'").replace("ʼ", "'")
    s = re.sub(r"\s+", " ", s)
    return s

def _match_any(q: str, patterns: list[str]) -> bool:
    return any(re.search(p, q) for p in patterns)

P_HOW_ARE_YOU = [
    r"\bяк\s+ти\b",
    r"\bяк\s+справ[иі]\b",
    r"\bяк\s+воно\b",
    r"\bяк\s+настр[оі]й\b",
    r"\bти\s+норм\b",
    r"\bшо\s+ти\b",
    r"\bщо\s+ти\b",
]
P_WHAT_DOING_NOW = [
    r"\bшо\s+робиш\b",
    r"\bщо\s+робиш\b",
    r"\bчим\s+займаєшс(я|ь)\b",
    r"\bшо\s+ти\s+робиш\s+зараз\b",
    r"\bщо\s+ти\s+робиш\s+зараз\b",
    r"\bзайнят(ий|а)\b",
]
P_WHAT_DID_YESTERDAY = [
    r"\bшо\s+робив\s+вчора\b",
    r"\bщо\s+робив\s+вчора\b",
    r"\bвчора\s+шо\s+робив\b",
    r"\bвчора\s+що\s+робив\b",
    r"\bяк\s+вчора\b",
]
P_HOW_DAY = [
    r"\bяк\s+день\b",
    r"\bяк\s+сьогодн(і|я)\b",
    r"\bяк\s+минув\s+день\b",
    r"\bщо\s+по\s+дню\b",
]

R_HOW_ARE_YOU = [
    "Я в ресурсі 😼🍃",
    "Квітну потроху 🌱",
    "Я тут, на звʼязку 🌿",
    "Все рівно й тихо ✨🌿",
    "Тепло. Як чай, що не обпікає 🍵🌿",
    "Відчуваю вайб чату 😼🌿",
]
R_WHAT_DOING_NOW = [
    "Слухаю чат і тримаю атмосферу 🌿😼",
    "Квітну й сторожую спокій 🪴👀",
    "Пильную, щоб ніхто не сумував 🌱",
    "Підкручую листочки, щоб було красиво 🍃✨",
]
R_WHAT_DID_YESTERDAY = [
    "Вчора тримав атмосферу і слухав людей 🌿",
    "Вчора — чай, тиша і трохи розмов 🍵🌿",
    "Вчора було тихо. Я люблю тихі дні 🌿",
]
R_HOW_DAY = [
    "Сьогодні рівно. Трохи справ — трохи спокою 🌿",
    "День тихий. Я такі люблю 🍃",
    "Сьогодні я на твоєму боці 😼🍃",
]

SMALLTALK = [
    (P_HOW_ARE_YOU, R_HOW_ARE_YOU),
    (P_WHAT_DOING_NOW, R_WHAT_DOING_NOW),
    (P_WHAT_DID_YESTERDAY, R_WHAT_DID_YESTERDAY),
    (P_HOW_DAY, R_HOW_DAY),
]

def _one(seq: list[str]) -> str:
    return random.choice(seq)

def _dedupe_join(parts: list[str]) -> str:
    out = []
    seen = set()
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return " ".join(out).strip()

TAIL_QUESTIONS = [
    "А ти як?", "Що нового?", "Розкажеш коротко? 👀", "Хочеш — просто виговорись 🌿"
]
TAIL_VIBES = [
    "Я поруч 🌿", "Тримаю атмосферу 💚", "Спокійно, я тут 👀", "Мʼяко, без поспіху 🍃"
]
TAIL_SUPPORT = [
    "Якщо важко — я підтримаю 🌿", "Навіть маленький крок — це крок 🌱", "Ти не один 💚"
]
HEADERS = ["Хей 😼", "Оу 👀", "Слухаю 🌿", "Ага ✨", ""]

def combine_reply(base: str, kind: str) -> str:
    base = (base or "").strip()
    if not base:
        return base

    parts = []
    if random.random() < 0.35:
        h = _one(HEADERS).strip()
        if h:
            parts.append(h)

    parts.append(base)

    roll = random.random()
    tails_count = 1 if roll < 0.55 else (2 if roll < 0.75 else 0)

    if kind in ("how", "day"):
        tails_pool = TAIL_QUESTIONS + TAIL_VIBES + TAIL_SUPPORT
    elif kind in ("doing", "yesterday"):
        tails_pool = TAIL_VIBES + TAIL_QUESTIONS
    else:
        tails_pool = TAIL_VIBES + TAIL_QUESTIONS + TAIL_SUPPORT

    if tails_count >= 1:
        parts.append(_one(tails_pool))
    if tails_count >= 2:
        parts.append(_one(tails_pool))

    result = _dedupe_join(parts)
    if len(result) > 260:
        result = _dedupe_join(parts[:3])

    return result

def detect_smalltalk(q: str) -> str | None:
    qq = _norm_ua(q)
    for patterns, replies in SMALLTALK:
        if _match_any(qq, patterns):
            base = random.choice(replies)
            if patterns is P_HOW_ARE_YOU:
                kind = "how"
            elif patterns is P_WHAT_DOING_NOW:
                kind = "doing"
            elif patterns is P_WHAT_DID_YESTERDAY:
                kind = "yesterday"
            elif patterns is P_HOW_DAY:
                kind = "day"
            else:
                kind = "generic"
            return combine_reply(base, kind)
    return None


# Команди/довідка
def commands_text() -> str:
    return (
        f"Ось що я вмію {n_emo()} (повний список):\n\n"
        "• Нері, привіт\n"
        "• Нері, привітайся (привітання новачку)\n"
        "• Нері, що ти / як ти / шо робиш / як справи / шо робив вчора\n"
        "• Нері, погода в <місто>\n"
        "• Нері, скільки тобі років\n"
        "• Нері, коли в тебе день народження\n"
        "• Нері, хто такий/така <імʼя>\n\n"
        "Якщо напишеш криво — нічого, я все одно спробую зрозуміти 🌿"
    )


def clean_text(text: str) -> str:
    t = text.strip()
    t = NERI_PREFIX.sub("", t)
    t = re.sub(r"\s+", " ", t)
    return t.lower()


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
    raw_text = message.get("text", "")
    text = raw_text.lower()

    reply = None

    if text == "/start":
        reply = (
            "Привіт ✨ Я Нері.\n\n"
            "Я маскот і символ команди 💚🌿\n\n"
            "Спробуй:\n"
            "• Нері, привіт\n"
            "• Нері, привітайся\n"
            "• Нері, що ти / як ти / шо робиш\n"
            "• Нері, погода в Києві\n"
            "• Нері, хто такий/така daze\n"
        )

    elif text == "/help":
        reply = commands_text()

    elif "нері" in text:
        q = clean_text(raw_text)

        if is_serious_topic(q):
            reply = serious_refusal()

        elif "привітайся" in q:
            reply = neri_style(
                "Привіт! Я Нері — маскот команди 💚🌿 Радий знайомству! "
                "Все потрібне знайдеш в чаті Work Neri ✨"
            )

        elif "погод" in q or "погода" in q:
            city = extract_city_from_query(q)
            reply = get_weather(city) if city else "Скажи місто 🌿 Наприклад: «Нері, погода в Києві»"

        else:
            # 1) хто такий/така (НОВЕ)
            who = answer_who_is(raw_text, q)
            if who:
                reply = who
            else:
                # 2) smalltalk (НОВЕ)
                st = detect_smalltalk(q)
                if st:
                    reply = neri_style(st)
                else:
                    # 3) базові відповіді
                    reply = neri_style(random.choice([
                        "Я тут 🌿 Скажи 1–2 ключові слова — і я підхоплю ✨",
                        "Я не зловив тему 🍃 Але я поруч. Кинь контекст одним рядком 👀",
                        "Я підвис на сенсі 😼🌿 Дай підказку: про людей, про чат чи про погоду?",
                        "Я можу відповісти краще, якщо скажеш: це питання про команду чи просто побалакати? 🌿✨",
                    ]))

    if reply:
        send_message(chat_id, reply)

    return {"ok": True}
