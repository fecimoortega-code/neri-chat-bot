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

# ===== “екстравертність” =====
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

    # емодзі інколи
    if random.random() < 0.25 and len(t) < 260:
        if not t.endswith(("🌿","✨","💚","😼","👀","🍃","🌱","🍀","🪴","🌸","🌼")):
            t = t + " " + n_emo()

    t = enforce_neri_pronouns(t)
    return t

NERI_AGE = 2
NERI_BDAY = "16.09.2025"

# ===== Pronouns Q/A =====
def is_pronouns_query(q: str) -> bool:
    return ("займенник" in q) or ("займенники" in q) or ("pronouns" in q)

def pronouns_reply() -> str:
    return "Мої займенники — він/вони 🌿"

# ===== Mom/Dad =====
def is_mom_query(q: str) -> bool:
    return ("хто" in q) and ("мама" in q or "матуся" in q or "матi" in q or "мать" in q)

def is_dad_query(q: str) -> bool:
    return ("хто" in q) and ("тато" in q or "татусь" in q or "батько" in q)

MOM_REPLIES = [
    "Рітерум (Рум) — моя матуся 💚🌿",
    "Моя матуся — Рітерум. Її ще звуть Рум 🌿✨",
    "Рум — матуся. Тут без варіантів 😼🌿",
]

DAD_REPLIES = [
    "Лірен — мій татусь 💚🌿",
    "Мій татусь — Лірен. Сильна опора 🌳✨",
    "Лірен — татусь. Я це знаю серцем 🌿",
]

# ===== Team profiles (хто такий/така) =====
TEAM_PROFILES = {
    "nerineris": {"name": "Nerineris", "ua": "Нері", "role": "Найкраща пусічка у СВІТІ", "link": "https://t.me/Nerineris"},
    "riterum":   {"name": "Riterum (Рум)", "ua": "Рітерум", "role": "Лідер, вокал, переклад, SMM", "link": "https://t.me/AriaTerum"},
    "liren":     {"name": "LiRen", "ua": "Лірен", "role": "Лідер, вокал, ілюстрації, переклад", "link": "https://t.me/LiRen_Arts"},
    "daze":      {"name": "daze", "ua": "Дейз", "role": "Адмін, відео", "link": "https://t.me/korobkadaze"},
    "tori":      {"name": "Tori_frr", "ua": "Торі", "role": "Адмін, вокал, переклад, ілюстрації, відео", "link": "https://t.me/Kaganuka"},
    "pina":      {"name": "ПІНОПЛАСТІВОЧКА", "ua": "Піна", "role": "Вокал, ілюстрації, переклад", "link": "https://t.me/vezha_pinoplastivochky"},
    "alyvian":   {"name": "Alyvian", "ua": "Алувіан", "role": "Адмін, вокал, гармонії", "link": "https://t.me/alyviancovers"},
    "miraj":     {"name": "Miraj", "ua": "Мірай", "role": "Вокал, гармонії", "link": ""},
    "stellar":   {"name": "StellarSkriM", "ua": "Стеллар", "role": "Зведення", "link": "https://t.me/StellarSkriMRoom"},
    "rybka":     {"name": "Рибка", "ua": "Рибка", "role": "Відео", "link": ""},
    "lee":       {"name": "Lee", "ua": "Лі", "role": "Ілюстрації", "link": "https://t.me/artdisainli"},
    "moka":      {"name": "мокатроля", "ua": "Мока", "role": "Ілюстрації", "link": "https://x.com/mokatrola"},
    "inky":      {"name": "InkyLove", "ua": "Інкі", "role": "Вокал", "link": "https://t.me/inky_Love_Ua"},
    "lesya":     {"name": "Леся/moemoenya", "ua": "Леся", "role": "Ілюстрації", "link": "https://t.me/moemoenya"},
    "mari":      {"name": "MARi", "ua": "Марі", "role": "Вокал, зведення, гармонії", "link": "https://t.me/maricovers"},
    "dreamu":    {"name": "Dreamu", "ua": "Дрімі", "role": "Ілюстрації", "link": ""},
    "illya":     {"name": "Ілля", "ua": "Ілля", "role": "Зведення", "link": ""},
    "pechenieg": {"name": "pechenig", "ua": "печеніг", "role": "Ілюстрації, відео", "link": "https://t.me/pechenig_tg"},
    "zhuk":      {"name": "Дмитро Жук", "ua": "Жук", "role": "Ілюстрації", "link": "https://t.me/duke_zhukem"},
    "azri":      {"name": "Azri", "ua": "Азрі", "role": "Вокал, зведення", "link": ""},
}

PROFILE_ALIASES = {
    "nerineris": ["nerineris", "нері", "neri"],
    "riterum":   ["riterum", "рітерум", "рум", "rit", "ритерум"],
    "liren":     ["liren", "лірен", "ліренчик", "лірену", "лірена"],
    "daze":      ["daze", "дейз", "deiz"],
    "tori":      ["tori", "tori_frr", "торі", "тори"],
    "pina":      ["піна", "пінопластівочка", "pinoplastivochka", "pina"],
    "alyvian":   ["alyvian", "алувіан", "aluvian"],
    "miraj":     ["miraj", "мірай"],
    "stellar":   ["stellarskrim", "stellar", "стеллар", "стелларскрім"],
    "rybka":     ["рибка"],
    "lee":       ["lee", "лі"],
    "moka":      ["мока", "мокатрола", "mokatrola"],
    "inky":      ["inky", "inkylove", "інкі"],
    "lesya":     ["леся", "moemoenya"],
    "mari":      ["mari", "марі", "maricovers"],
    "dreamu":    ["dreamu", "дрімі", "dreamy"],
    "illya":     ["ілля", "illya"],
    "pechenieg": ["печеніг", "pechenieg", "pechenig"],
    "zhuk":      ["жук", "dmytro", "дуке", "duke_zhukem", "дмитро жук"],
    "azri":      ["азрі", "azri", "azry"],
}

ALIAS_TO_PROFILE_KEY: dict[str, str] = {}
for key, als in PROFILE_ALIASES.items():
    for a in als:
        ALIAS_TO_PROFILE_KEY[a.lower()] = key

def _clean_name_token(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("’", "'").replace("ʼ", "'")
    s = re.sub(r"^[^\wа-щьюяєіїґ\-']+|[^\wа-щьюяєіїґ\-']+$", "", s, flags=re.IGNORECASE)
    return s

def canonical_profile_key(name_raw: str) -> str:
    key = _clean_name_token(name_raw)
    if not key:
        return ""
    return ALIAS_TO_PROFILE_KEY.get(key, key)

def extract_quoted_name(raw: str) -> str | None:
    m = re.search(r"[\"“”'‘’](.+?)[\"“”'‘’]", raw)
    return m.group(1).strip() if m else None

# === UPDATE: нормальне витягування імені після "до/про" ===
def extract_name_after_preposition(q: str, prep: str) -> str | None:
    """
    Витягує ім'я після 'до' або 'про'.
    Працює з: "як ти відносишся до торі?" / "твоє відношення до Рум" / "що думаєш про Дейза"
    """
    # бере слово/фразу після preposition до кінця або до знаків пунктуації
    m = re.search(rf"(?:\b{prep}\b)\s+(.+)$", q)
    if not m:
        return None

    tail = (m.group(1) or "").strip()

    # прибираємо хвости типу "будь ласка", "плиз" і т.д. (за потреби можна розширити)
    tail = re.sub(r"\b(будь\s+ласка|будь-ласка|пліз|плиз)\b.*$", "", tail).strip()

    # якщо там кілька слів — беремо перші 2, але перевіримо по алиасам
    parts = [p for p in re.split(r"\s+", tail) if p]
    if not parts:
        return None

    # 2-слова (на випадок "дмитро жук")
    if len(parts) >= 2:
        cand2 = _clean_name_token(parts[0] + " " + parts[1])
        if cand2 and cand2 in ALIAS_TO_PROFILE_KEY:
            return parts[0] + " " + parts[1]

    # 1-слово
    return parts[0]

def answer_who_is(raw_text: str, q: str) -> str | None:
    # ТІЛЬКИ явні формулювання
    if not (
        re.search(r"\bхто\s+(такий|така|це)\b", q)
        or re.search(r"\bщо\s+за\b", q)
        or re.search(r"\bхто\b.*\bце\b", q)
    ):
        return None

    name = extract_quoted_name(raw_text)

    if not name:
        # пробуємо після "хто такий/така/це" або "що за"
        m = re.search(r"\b(такий|така|це|за)\b\s+(.+)$", q)
        if m:
            tail = m.group(2).strip()
            parts = [p for p in re.split(r"\s+", tail) if p]
            if parts:
                if len(parts) >= 2:
                    cand2 = _clean_name_token(parts[0] + " " + parts[1])
                    if cand2 and cand2 in ALIAS_TO_PROFILE_KEY:
                        name = parts[0] + " " + parts[1]
                    else:
                        name = parts[0]
                else:
                    name = parts[0]

    if not name:
        return None

    k = canonical_profile_key(name)
    prof = TEAM_PROFILES.get(k)
    if not prof:
        return None

    line = f"{prof['name']} — {prof['role']} 🌿"
    if prof.get("link"):
        line += f"\n{prof['link']}"
    return neri_style(line)

# ===== Member opinions (як відносишся/що думаєш) =====
MEMBER_OPINIONS = {
    "riterum": ["Рітерум (Рум) — моя матуся 💚🌿", "Рум — матуся. Теплий корінь команди 🌿✨"],
    "liren":   ["Лірен — мій татусь 💚🌿", "Лірен — татусь. Сильна опора 🌳✨"],
    "tori":    ["Торі? Мені подобаються її вушка 🐾🌿", "Торі — вайбова. І вушка топ ✨🌿"],
    "daze":    ["Дейз — мій відео-двигун 🌿🎬", "Дейз робить рух і ритм. Це повага 😼🌿"],
    "pina":    ["Піна — голос, що цвіте 🌸💚", "Піна — дуже ніжний вайб 🌿✨"],
    "alyvian": ["Алувіан — справжній вайб 🍃😼", "Алувіан — звучить сильно 🌿✨"],
    "miraj":   ["Мірай — м’яка як вечірній вітер 🍃✨", "Мірай — тепла присутність 🌿💚"],
    "stellar": ["Стеллар — зведення як зорі на небі 🌙✨", "Стеллар — дуже потужно по звуку 🌿✨"],
    "rybka":   ["Рибка — монтаж летить, як листя у вітрі 🍃✨", "Рибка — нереальний монтажер 🌿🔥"],
    "lee":     ["Лі — стилю вистачить на цілий сад 🌿✨", "Лі — неймовірний артстайл 🎨🌿"],
    "moka":    ["Мока — малює так, що хочеться квітнути 🌱💚", "Мока — дуже гарні арти 🌿✨"],
    "inky":    ["Інкі — загадка. Але загадки теж гарні 🍃✨", "Інкі — я тримаю їй місце в саду 🌿"],
    "lesya":   ["Леся — оце енергія! 🌿😼", "Леся — прям СОНЦЕ ✨🌿"],
    "mari":    ["Марі — голос, що гріє 🌞🌿", "Марі — неймовірний вокал 🎤🌿"],
    "dreamu":  ["Дрімі — малюнки як сон 🌙🌿", "Дрімі — дуже ніжні арти 🌿✨"],
    "illya":   ["Ілля — звук як чисте повітря 🌿✨", "Ілля — зведення нереальні 🎛️🌿"],
    "pechenieg":["печеніг — інколи приносить легенди 🍃✨", "печеніг — вайбово і творчо 😼🌿"],
    "zhuk":    ["Жук — арти як вибух цвіту 🌸✨", "Жук — НЕРЕАЛЬНІ АРТИ!! 🎨🔥🌿"],
    "azri":    ["Азрі — фуряшки наступають… і я не проти 😼🍃", "Азрі — атака фуряшками 🐾🌿"],
}

def handle_member_opinion(raw_text: str, q: str) -> str | None:
    # ЯВНО: "як ти відносишся до X" / "твоє відношення до X" / "що думаєш про X"
    if not re.search(r"(відносиш|відношенн|ставиш|думаєш)", q):
        return None

    name = extract_quoted_name(raw_text)

    # === UPDATE: беремо ім'я після ДО/ПРО, а не "останнє слово" ===
    if not name:
        if re.search(r"\bдо\b", q) and re.search(r"(відносиш|відношенн|ставиш)", q):
            name = extract_name_after_preposition(q, "до")
        elif re.search(r"\bпро\b", q) and re.search(r"\bдумаєш\b", q):
            name = extract_name_after_preposition(q, "про")

    # запасний варіант (старий): останнє слово
    if not name:
        parts = q.split()
        name = parts[-1] if parts else ""

    k = canonical_profile_key(name)

    if k in MEMBER_OPINIONS:
        return neri_style(random.choice(MEMBER_OPINIONS[k]))

    # fallback якщо ім'я не знайшли
    return neri_style(f"Я думаю, що {name} — частина нашого саду. І це вже багато 💚")

# ===== "покарай <ім'я>" (жартівливо) =====
def is_punish_query(q: str) -> bool:
    return ("покар" in q) or ("накаж" in q) or ("мут" in q)

PUNISH_TEMPLATES = [
    "⚖️ {name}, вирок від Нері: 10 хвилин тиші і 1 (одна) добра справа. Потім — назад у сад {emo}💚",
    "🌿 {name}, я тебе не бʼю — я тебе виховую: виправляйся і квітни {emo}😼",
    "🍃 {name}, штраф: повернути атмосферу на місце. Плюс 3 компліменти команді {emo}✨",
    "🪴 {name}, покарання: відкласти токс і принести чай/воду. Гідратація — це закон {emo}",
    "🌸 {name}, вирок: 5 хвилин 'я хороший/хороша' і жодних сварок. Я стежу 👀 {emo}",
]
PUNISH_EXTRA = [
    "Якщо не виконаєш — листочок буде сумувати 🌿😿",
    "Виконаєш — отримаєш +1 обійм по-нерівськи 🍃💚",
    "Це все жарт, але атмосфера — серйозна 😼🌿",
]

def extract_name_after_keyword(q: str, keyword_root: str) -> str | None:
    parts = q.split()
    for i, w in enumerate(parts):
        if keyword_root in w and i + 1 < len(parts):
            name = parts[i + 1]
            name = re.sub(r"[^\wа-щьюяєіїґ\-’ʼ]", "", name, flags=re.IGNORECASE)
            return name.strip() if name else None
    return None

def handle_punish(raw_text: str, q: str) -> str | None:
    if not is_punish_query(q):
        return None

    name = extract_quoted_name(raw_text)
    if not name:
        name = (
            extract_name_after_keyword(q, "покар")
            or extract_name_after_keyword(q, "накаж")
            or extract_name_after_keyword(q, "мут")
        )

    if not name:
        return neri_style("Кого карати? Напиши так: «Нері, покарай Торі» 👀")

    k = canonical_profile_key(name)
    if k == "nerineris" or "нері" in (name or "").lower():
        return neri_style("Я себе не караю 😼🌿 Я краще квітну. А кого караємо?")

    nice = name.strip()
    prof = TEAM_PROFILES.get(k)
    if prof:
        nice = prof["name"]

    emo = n_emo()
    base = random.choice(PUNISH_TEMPLATES).format(name=nice, emo=emo)
    tail = random.choice(PUNISH_EXTRA)
    return neri_style(f"{base}\n{tail}")

# ===== політика/війна — табу =====
SERIOUS_KEYWORDS = ["політик", "вибор", "парті", "війна", "фронт", "зброя", "ракета"]
def is_serious_topic(q: str) -> bool:
    return any(k in q for k in SERIOUS_KEYWORDS)

def serious_refusal() -> str:
    return "Я не говорю про політику/війну 🌿 Давай краще про щось тепле й командне 💚"

# ===== Команди/довідка =====
def is_cmds_query(q: str) -> bool:
    if re.search(r"\bкоманд(и|а)?\b", q):
        return True
    if ("що" in q and "вмі" in q):
        return True
    return False

# ===== Random member (випадковий учасник) ✅ ДОДАНО =====
def is_random_member_query(q: str) -> bool:
    return ("випадков" in q) and ("учасник" in q or "учасника" in q or "мембер" in q or "member" in q)

def random_member_reply() -> str:
    k = random.choice(list(TEAM_PROFILES.keys()))
    prof = TEAM_PROFILES[k]
    line = f"Випадковий учасник: {prof['name']} 🌿"
    if prof.get("link"):
        line += f"\n{prof['link']}"
    return line

# ===== "Нері, привіт" ✅ ДОДАНО =====
def is_hi_query(q: str) -> bool:
    qq = (q or "").strip().lower()
    return qq in ("привіт", "привiт", "хай", "хей", "йо", "hello", "hi")

HI_REPLIES = [
    "Привіт 😼🌿 Я Нері. Як ти?",
    "Хей-хей! Я тут 🌿✨ Що робимо?",
    "Привіт! Тримаю атмосферу 💚🌿",
    "Оу 👀 Привіт-привіт! Як день?",
]

def hi_reply() -> str:
    return random.choice(HI_REPLIES)

def commands_text() -> str:
    return (
        f"Ось мої основні команди {n_emo()}:\n\n"
        "• Нері, привіт\n"
        "• Нері, як ти / як справи / шо робиш / шо робив вчора\n"
        "• Нері, команди / що ти вмієш\n"
        "• Нері, привітайся\n"
        "• Нері, погода в <місто>\n"
        "• Нері, скільки тобі років\n"
        "• Нері, коли в тебе день народження\n"
        "• Нері, хто твоя мама / хто твій тато\n"
        "• Нері, хто такий/така <ім’я>\n"
        "• Нері, як ти відносишся до <ім’я> / що ти думаєш про \"<ім’я>\"\n"
        "• Нері, монетка / кубик / число\n"
        "• Нері, покарай <ім’я> (жартівливо)\n"
        "• Нері, назви випадкового учасника\n\n"
        "Якщо напишеш криво — нічого, я все одно спробую зрозуміти 🌿"
    )

ABOUT_REPLIES = [
    "Я Нері — маскот і символ команди 💚🌿 Їхня душа й атмосфера ✨",
    "Нері — це не просто імʼя. Це символ команди 🌿✨",
    "Я Нері: маскот, талісман і тиха сила команди 🌱✨",
    "Я тут для допомоги, ігор і атмосфери 💚🌿",
    "Я ніжний і турботливий, АЛЕ ДУЖЕ ТОВАРИСЬКИЙ 😼🌿✨",
    "Я люблю побазікати, природу, музику і зелений чай 🍵🌿",
]

INTERESTING_REPLIES = [
    "Іноді найкраща атмосфера — коли всі просто тихо поруч 🌿",
    "Коли чат теплий — я буквально квітну 🌱✨",
    "Маленькі кроки теж кроки. Особливо якщо вони в правильний бік 🍃",
    "Якщо ти читаєш це — ти вже тут. А це багато ✨🌿",
    "Видих. Ще один. І стає легше 🍃🌿",
]

def is_about_query(q: str) -> bool:
    return ("розкажи" in q and "про" in q and "себе") or ("хто" in q and "ти" in q)

def is_interesting_query(q: str) -> bool:
    return ("розкажи" in q and ("цікав" in q or "цікавеньк" in q)) or ("розкажи" in q and "щось" in q)

def is_age_query(q: str) -> bool:
    return ("скільки" in q and "рок" in q) or ("вік" in q)

def is_bday_query(q: str) -> bool:
    return ("день" in q and "народж") or ("коли" in q and "народж" in q)

def is_greet_new_query(q: str) -> bool:
    return "привітайся" in q or "привітай" in q

def greet_new_member_text() -> str:
    return (
        "Привіт! Я Нері — маскот команди 💚🌿 Радий знайомству!\n"
        "Все потрібне ти знайдеш у чаті Work Neri ✨"
    )

# ===== Smalltalk (багато відповідей) + combiner =====
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
]
P_WHAT_DOING_NOW = [
    r"\bшо\s+робиш\b",
    r"\bщо\s+робиш\b",
    r"\bчим\s+займаєшс(я|ь)\b",
]
P_WHAT_DID_YESTERDAY = [
    r"\bшо\s+робив\s+вчора\b",
    r"\bщо\s+робив\s+вчора\b",
    r"\bяк\s+вчора\b",
]
P_HOW_DAY = [
    r"\bяк\s+день\b",
    r"\bяк\s+сьогодн(і|я)\b",
    r"\bщо\s+по\s+дню\b",
]

R_HOW_ARE_YOU = [
    "Я окей 🌿 Спокійно, тепло.",
    "Квітну потроху 🌱",
    "Я тут, на звʼязку 😼🌿",
    "Я в ресурсі 😼🍃",
    "Тепло. Як чай, що не обпікає 🍵🌿",
]
R_WHAT_DOING_NOW = [
    "Слухаю чат і тримаю атмосферу 🌿😼",
    "Зараз? Дихаю зеленим чаєм уявно 🍵🌿",
    "Я тут — відповідаю, допомагаю, несу вайб ✨🌿",
]
R_WHAT_DID_YESTERDAY = [
    "Вчора? Тримав атмосферу і слухав людей 🌿",
    "Вчора — чай, тиша і трохи розмов 🍵🌿",
    "Вчора допомагав, коли мене кликали 👀🌿",
]
R_HOW_DAY = [
    "Сьогодні рівно. Трохи справ — трохи спокою 🌿",
    "День тихий. Я такі люблю 🍃",
    "День як чай: якщо не поспішати — ідеально 🍵",
]

SMALLTALK = [
    (P_HOW_ARE_YOU, R_HOW_ARE_YOU, "how"),
    (P_WHAT_DOING_NOW, R_WHAT_DOING_NOW, "doing"),
    (P_WHAT_DID_YESTERDAY, R_WHAT_DID_YESTERDAY, "yesterday"),
    (P_HOW_DAY, R_HOW_DAY, "day"),
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
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return " ".join(out).strip()

TAIL_QUESTIONS = [
    "А ти як?", "Що нового?", "Що в тебе зараз на думці?", "Розкажеш коротко?",
]
TAIL_VIBES = [
    "Я поруч 🌿", "Тримаю атмосферу 💚", "Спокійно, я тут 👀",
]
TAIL_SUPPORT = [
    "Якщо важко — я підтримаю 🌿", "Дихай: вдих… видих… 🍃", "Ти не один 💚",
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

    tails_pool = TAIL_VIBES + TAIL_QUESTIONS + (TAIL_SUPPORT if kind in ("how", "day") else [])
    if random.random() < 0.60:
        parts.append(_one(tails_pool))
    if random.random() < 0.25:
        parts.append(_one(tails_pool))

    res = _dedupe_join(parts)
    if len(res) > 260:
        res = _dedupe_join(parts[:3])
    return res

def detect_smalltalk(q: str) -> str | None:
    qq = _norm_ua(q)

    block = ["вмі", "команд", "віднос", "відношенн", "ставиш", "думаєш", "хто", "покар", "накаж", "мут", "погод", "рок", "народж", "привітай", "займенник"]
    if any(b in qq for b in block):
        return None

    for patterns, replies, kind in SMALLTALK:
        if _match_any(qq, patterns):
            base = random.choice(replies)
            return combine_reply(base, kind)

    return None

# ===== Misc games =====
def coin():
    return random.choice(["🪙 Орел", "🪙 Решка"])

def dice():
    return f"🎲 Випало: {random.randint(1, 6)}"

def number_1_100():
    return f"🔢 Моє число: {random.randint(1, 100)}"

# ===== clean =====
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
            "• Нері, команди\n"
            "• Нері, привітайся\n"
            "• Нері, погода в Києві\n"
            "• Нері, хто такий Рум\n"
            "• Нері, як ти відносишся до Торі\n"
            "• Нері, покарай Торі"
        )

    elif text == "/help":
        reply = commands_text()

    elif "нері" in text:
        q = clean_text(raw_text)

        # табу
        if is_serious_topic(q):
            reply = serious_refusal()

        # ===== "Нері, привіт" ✅ ДОДАНО =====
        elif is_hi_query(q):
            reply = neri_style(hi_reply())

        # займенники ✅ ДОДАНО
        elif is_pronouns_query(q):
            reply = neri_style(pronouns_reply())

        # погода
        elif "погод" in q or "погода" in q:
            city = extract_city_from_query(q)
            reply = get_weather(city) if city else "Скажи місто 🌿 Наприклад: «Нері, погода в Києві»"

        # ===== ігри (монетка/кубик/число) ✅ ДОДАНО =====
        elif q.strip() in ("монетка", "орел решка", "орел/решка", "орел", "решка"):
            reply = neri_style(coin())
        elif q.strip() in ("кубик", "дай кубик", "кістка"):
            reply = neri_style(dice())
        elif q.strip() in ("число", "дай число", "рандом число", "рандомне число"):
            reply = neri_style(number_1_100())

        # ===== випадковий учасник ✅ ДОДАНО =====
        elif is_random_member_query(q):
            reply = neri_style(random_member_reply())

        else:
            # 0) покарай (жарт)
            punish = handle_punish(raw_text, q)
            if punish:
                reply = punish

            # 1) команди
            elif is_cmds_query(q):
                reply = commands_text()

            # 2) привітання нового учасника
            elif is_greet_new_query(q):
                reply = neri_style(greet_new_member_text())

            # 3) про себе
            elif is_about_query(q):
                reply = neri_style(random.choice(ABOUT_REPLIES))

            # 4) щось цікаве
            elif is_interesting_query(q):
                reply = neri_style(random.choice(INTERESTING_REPLIES))

            # 5) вік / день народження
            elif is_age_query(q):
                reply = neri_style(random.choice([
                    f"Мені зараз {NERI_AGE}. Я ще молодий, але росту 🌱",
                    f"{NERI_AGE}. І з кожним днем я квітну сильніше 🌿",
                ]))

            elif is_bday_query(q):
                reply = neri_style(random.choice([
                    f"Мій день народження — {NERI_BDAY} 🌿",
                    f"Я святкую {NERI_BDAY}. Запамʼятай як теплу дату ✨",
                ]))

            # 6) мама/тато (ПРЯМО)
            elif is_mom_query(q):
                reply = neri_style(random.choice(MOM_REPLIES))

            elif is_dad_query(q):
                reply = neri_style(random.choice(DAD_REPLIES))

            else:
                # 7) хто такий/така (ОКРЕМО)
                who = answer_who_is(raw_text, q)
                if who:
                    reply = who
                else:
                    # 8) як відносишся/думаєш (ОКРЕМО)
                    op = handle_member_opinion(raw_text, q)
                    if op:
                        reply = op
                    else:
                        # 9) smalltalk
                        st = detect_smalltalk(q)
                        if st:
                            reply = neri_style(st)
                        else:
                            # 10) розумний фолбек
                            reply = neri_style(random.choice([
                                "Я підвис на сенсі 😼🌿 Дай 1–2 ключові слова — і я підхоплю ✨",
                                "Я не зловив тему 🍃 Але я поруч. Кинь контекст одним рядком 👀",
                                "Окей, я тут 🌿 Це про команду, про погоду, чи просто побалакати? ✨",
                                "Я можу відповісти краще, якщо скажеш: це питання про людей/чат чи щось інше 🌱",
                            ]))

    # базові штуки без "нері" (якщо хочеш — можна прибрати)
    else:
        if text.strip() in ("монетка", "орел решка"):
            reply = neri_style(coin())
        elif text.strip() in ("кубик", "дай кубик"):
            reply = neri_style(dice())
        elif text.strip() in ("число", "дай число"):
            reply = neri_style(number_1_100())

    if reply:
        send_message(chat_id, reply)

    return {"ok": True}
