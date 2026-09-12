import urllib.parse
import urllib.request
import psycopg2
import json
import re
import os
import threading
import time
import json as json_module

from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    session,
    Response,
    stream_with_context
)

from google import genai

from chat_history import (
    add_chat,
    load_history,
    delete_chat,
    rename_chat
)

from memory import (
    load_memory,
    update_memory
)

from bs4 import BeautifulSoup


# ==========================================
# DATA FOLDER
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

os.makedirs(DATA_DIR, exist_ok=True)


def load_users():

    if not os.path.exists(USERS_FILE):
        return []

    try:

        with open(
            USERS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return []


def save_users(users):

    with open(
        USERS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            users,
            file,
            indent=4,
            ensure_ascii=False
        )


# ==========================================
# APP
# ==========================================

SECRET_KEY = os.environ.get(
    "FLASK_SECRET_KEY"
)

if not SECRET_KEY:

    raise RuntimeError(
        "FLASK_SECRET_KEY is not set"
    )


app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("RENDER") == "true"
)


# ==========================================
# DATABASE
# ==========================================

def get_db_connection():

    database_url = os.environ.get(
        "DATABASE_URL"
    )

    if not database_url:

        raise RuntimeError(
            "DATABASE_URL is not set"
        )

    return psycopg2.connect(
        database_url
    )


def init_db():

    conn = get_db_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    username TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (username, key)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    messages JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()

    finally:

        conn.close()


# ==========================================
# GEMINI
# ==========================================

MODEL = "gemini-3.6-flash"

FALLBACK_MODEL = "gemini-2.5-flash-lite"

client = genai.Client()


# ==========================================
# MEMORY HELPERS
# ==========================================

def clean_value(value):

    value = str(value).strip()

    value = re.sub(
        r"\s+(hai|hain|is)$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = value.rstrip(
        ".,!?"
    ).strip()

    return value


def save_memory(
    key,
    value,
    user_memory
):

    username = session.get(
        "username"
    )

    if not username:
        return

    value = clean_value(
        value
    )

    if not value:
        return

    update_memory(
        key,
        value,
        username
    )

    user_memory[key] = value

    print(
        f"Memory saved: {key} = {value}"
    )


# ==========================================
# AUTOMATIC MEMORY DETECTION
# ==========================================

def detect_memory(
    message,
    user_memory
):

    text = message.strip()

    patterns = [

        (
            r"^(?:mera naam|my name is)\s+(.+?)(?:\s+hai)?[.!?]?$",
            "name"
        ),

        (
            r"^(?:main|mai)\s+(.+?)\s+me\s+padh(?:ta|ti)\s+hoon[.!?]?$",
            "college"
        ),

        (
            r"^(?:main|mai)\s+(.+?)\s+me\s+rehta\s+hoon[.!?]?$",
            "city"
        ),

        (
            r"^(?:meri city|my city)\s+(.+?)(?:\s+hai)?[.!?]?$",
            "city"
        ),

        (
            r"^(?:mera|meri)\s+(?:favorite|favourite)\s+game\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite game"
        ),

        (
            r"^my\s+(?:favorite|favourite)\s+game\s+is\s+(.+?)[.!?]?$",
            "favorite game"
        ),

        (
            r"^mujhe\s+(.+?)\s+pasand\s+hai[.!?]?$",
            "preference"
        ),

        (
            r"^(?:mera|meri)\s+(?:favorite|favourite)\s+color\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite color"
        ),

        (
            r"^my\s+(?:favorite|favourite)\s+color\s+is\s+(.+?)[.!?]?$",
            "favorite color"
        ),

        (
            r"^(?:mera|meri)\s+(?:favorite|favourite)\s+programming language\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite programming language"
        ),

        (
            r"^mera goal\s+(.+?)(?:\s+hai)?[.!?]?$",
            "goal"
        ),

        (
            r"^my goal is\s+(.+?)[.!?]?$",
            "goal"
        )
    ]

    for pattern, key in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        value = clean_value(
            match.group(1)
        )

        if not value:
            return

        if key == "preference":

            save_memory(
                "favorite",
                value,
                user_memory
            )

            return

        save_memory(
            key,
            value,
            user_memory
        )

        return


# ==========================================
# PERSONAL QUESTIONS
# ==========================================

def personal_answer(
    message,
    user_memory
):

    text = message.lower().strip()

    text = re.sub(
        r"[?.!]",
        "",
        text
    )

    # AI NAME

    if any(
        x in text
        for x in [
            "tumhara naam kya hai",
            "tumhare naam kya hai",
            "aapka naam kya hai",
            "aapke naam kya hai"
        ]
    ):

        return (
            "Mera naam Normal Chat hai."
        )

    # USER NAME

    if any(
        x in text
        for x in [
            "mera naam kya hai",
            "my name kya hai",
            "what is my name"
        ]
    ):

        if "name" in user_memory:

            return (
                f"Tumhara naam "
                f"{user_memory['name']} hai."
            )

        return (
            "Mujhe abhi tumhara naam nahi pata."
        )

    # FAVORITE GAME

    if "mera favorite game kya hai" in text:

        if "favorite game" in user_memory:

            return (
                f"Tumhara favorite game "
                f"{user_memory['favorite game']} hai."
            )

        return (
            "Mujhe abhi tumhara favorite game nahi pata."
        )

    # FAVORITE COLOR

    if "mera favorite color kya hai" in text:

        if "favorite color" in user_memory:

            return (
                f"Tumhara favorite color "
                f"{user_memory['favorite color']} hai."
            )

        return (
            "Mujhe abhi tumhara favorite color nahi pata."
        )

    # FAVORITE

    if "mera favorite kya hai" in text:

        if "favorite" in user_memory:

            return (
                f"Tumhe "
                f"{user_memory['favorite']} pasand hai."
            )

        return (
            "Mujhe abhi tumhara favorite nahi pata."
        )

    # COLLEGE

    if any(
        x in text
        for x in [
            "mera college kya hai",
            "mera college ka kya naam hai",
            "mere college ka kya naam hai",
            "what is my college"
        ]
    ):

        if "college" in user_memory:

            return (
                f"Tumhara college "
                f"{user_memory['college']} hai."
            )

        return (
            "Mujhe abhi tumhara college nahi pata."
        )

    # GOAL

    if "mera goal kya hai" in text:

        if "goal" in user_memory:

            return (
                f"Tumhara goal "
                f"{user_memory['goal']} hai."
            )

        return (
            "Mujhe abhi tumhara goal nahi pata."
        )

    # CITY

    if "meri city kya hai" in text:

        if "city" in user_memory:

            return (
                f"Tumhari city "
                f"{user_memory['city']} hai."
            )

        return (
            "Mujhe abhi tumhari city nahi pata."
        )

    return None


# ==========================================
# SIGNUP
# ==========================================

@app.route(
    "/signup",
    methods=["POST"]
)
def signup():

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "error": "Request data missing"
            }), 400

        username = str(
            data.get(
                "username",
                ""
            )
        ).strip()

        password = str(
            data.get(
                "password",
                ""
            )
        )

        if not username or not password:

            return jsonify({
                "error":
                "Username and password are required"
            }), 400

        if len(username) < 3:

            return jsonify({
                "error":
                "Username must be at least 3 characters"
            }), 400

        if len(password) < 8:

            return jsonify({
                "error":
                "Password must be at least 8 characters"
            }), 400

        password_hash = generate_password_hash(
            password
        )

        conn = get_db_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO users
                    (username, password)
                    VALUES (%s, %s)
                    """,
                    (
                        username,
                        password_hash
                    )
                )

            conn.commit()

        except psycopg2.errors.UniqueViolation:

            conn.rollback()

            return jsonify({
                "error":
                "Username already exists"
            }), 409

        finally:

            conn.close()

        session["username"] = username

        return jsonify({
            "message":
            "Signup successful",
            "username":
            username
        }), 201

    except Exception as error:

        print(
            "Backend error:",
            repr(error)
        )

        return jsonify({
            "error":
            str(error)
        }), 500


# ==========================================
# LOGIN
# ==========================================

@app.route(
    "/login",
    methods=["POST"]
)
def login():

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "error":
                "Request data missing"
            }), 400

        username = str(
            data.get(
                "username",
                ""
            )
        ).strip()

        password = str(
            data.get(
                "password",
                ""
            )
        )

        if not username or not password:

            return jsonify({
                "error":
                "Username and password are required"
            }), 400

        conn = get_db_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT username, password
                    FROM users
                    WHERE LOWER(username)
                    = LOWER(%s)
                    """,
                    (username,)
                )

                user = cursor.fetchone()

        finally:

            conn.close()

        if not user:

            return jsonify({
                "error":
                "Invalid username or password"
            }), 401

        stored_username, stored_password = user

        if not check_password_hash(
            stored_password,
            password
        ):

            return jsonify({
                "error":
                "Invalid username or password"
            }), 401

        session["username"] = stored_username

        return jsonify({
            "message":
            "Login successful",
            "username":
            stored_username
        }), 200

    except Exception as error:

        import traceback

        print(
            "========== LOGIN ERROR =========="
        )

        print(
            "ERROR:",
            repr(error)
        )

        traceback.print_exc()

        print(
            "================================="
        )

        return jsonify({
            "error":
            "Login error",
            "details":
            str(error)
        }), 500


# ==========================================
# LOGOUT
# ==========================================

@app.route(
    "/logout",
    methods=["POST"]
)
def logout():

    session.clear()

    return jsonify({
        "message":
        "Logged out successfully"
    })


# ==========================================
# CURRENT USER
# ==========================================

@app.route(
    "/me",
    methods=["GET"]
)
def me():

    username = session.get(
        "username"
    )

    if username:

        return jsonify({
            "logged_in":
            True,
            "username":
            username
        })

    return jsonify({
        "logged_in":
        False
    })


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    return send_from_directory(
        os.path.join(
            BASE_DIR,
            "frontend"
        ),
        "index.html"
    )


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route("/health")
def health():

    return jsonify({
        "status":
        "ok"
    })


# ==========================================
# REAL-TIME WEATHER
# ==========================================

def get_weather(city):

    try:

        city_encoded = urllib.parse.quote(
            city
        )

        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={city_encoded}"
            "&count=1"
            "&language=en"
            "&format=json"
        )

        with urllib.request.urlopen(
            geo_url,
            timeout=10
        ) as response:

            geo_data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        if not geo_data.get(
            "results"
        ):

            return (
                f"Sorry, mujhe '{city}' "
                "naam ki city nahi mili."
            )

        location = geo_data[
            "results"
        ][0]

        latitude = location[
            "latitude"
        ]

        longitude = location[
            "longitude"
        ]

        city_name = location[
            "name"
        ]

        country = location.get(
            "country",
            ""
        )

        timezone = location.get(
            "timezone",
            "auto"
        )

        weather_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}"
            f"&longitude={longitude}"
            "&current="
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "precipitation,"
            "weather_code,"
            "wind_speed_10m"
            f"&timezone="
            f"{urllib.parse.quote(timezone)}"
        )

        with urllib.request.urlopen(
            weather_url,
            timeout=10
        ) as response:

            weather_data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        current = weather_data.get(
            "current",
            {}
        )

        temperature = current.get(
            "temperature_2m"
        )

        feels_like = current.get(
            "apparent_temperature"
        )

        humidity = current.get(
            "relative_humidity_2m"
        )

        rain = current.get(
            "precipitation"
        )

        wind = current.get(
            "wind_speed_10m"
        )

        weather_code = current.get(
            "weather_code"
        )

        conditions = {

            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Foggy",
            51: "Light drizzle",
            53: "Drizzle",
            55: "Heavy drizzle",
            56: "Freezing drizzle",
            57: "Heavy freezing drizzle",
            61: "Light rain",
            63: "Rain",
            65: "Heavy rain",
            66: "Freezing rain",
            67: "Heavy freezing rain",
            71: "Light snow",
            73: "Snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Light rain showers",
            81: "Rain showers",
            82: "Heavy rain showers",
            85: "Light snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Heavy thunderstorm with hail"
        }

        condition = conditions.get(
            weather_code,
            "Unknown weather"
        )

        return (
            f"🌤️ Weather in "
            f"{city_name}, {country}\n\n"
            f"🌡️ Temperature: "
            f"{temperature}°C\n"
            f"🤒 Feels like: "
            f"{feels_like}°C\n"
            f"☁️ Condition: "
            f"{condition}\n"
            f"💧 Humidity: "
            f"{humidity}%\n"
            f"🌧️ Precipitation: "
            f"{rain} mm\n"
            f"💨 Wind speed: "
            f"{wind} km/h"
        )

    except Exception as error:

        print(
            "WEATHER ERROR:",
            repr(error)
        )

        return (
            "Sorry, weather service "
            "abhi available nahi hai."
        )


# ==========================================
# WEB SEARCH
# ==========================================

def web_search(
    query,
    max_results=5
):

    try:

        search_url = (
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote(query)
        )

        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            }
        )

        with urllib.request.urlopen(
            req,
            timeout=15
        ) as response:

            html = response.read().decode(
                "utf-8",
                errors="ignore"
            )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        results = []

        for result in soup.select(
            ".result"
        ):

            title_element = result.select_one(
                ".result__a"
            )

            snippet_element = result.select_one(
                ".result__snippet"
            )

            if not title_element:
                continue

            title = title_element.get_text(
                " ",
                strip=True
            )

            url = title_element.get(
                "href",
                ""
            )

            snippet = ""

            if snippet_element:

                snippet = snippet_element.get_text(
                    " ",
                    strip=True
                )

            if not title or not url:
                continue

            results.append({
                "title": title,
                "url": url,
                "snippet": snippet
            })

            if len(results) >= max_results:
                break

        print(
            "WEB SEARCH:",
            query,
            "RESULTS:",
            len(results)
        )

        return results

    except Exception as error:

        print(
            "WEB SEARCH ERROR:",
            repr(error)
        )

        return []


def format_web_results(results):

    if not results:
        return ""

    lines = []

    for index, result in enumerate(
        results,
        start=1
    ):

        lines.append(
            f"{index}. "
            f"{result['title']}\n"
            f"URL: {result['url']}\n"
            f"{result['snippet']}"
        )

    return "\n\n".join(
        lines
    )


# ==========================================
# GEMINI GENERATION HELPER
# ==========================================

def generate_ai_reply(
    prompt,
    use_web_search=False
):

    response = None
    last_error = None

    models_to_try = [
        MODEL,
        FALLBACK_MODEL
    ]

    for current_model in models_to_try:

        for attempt in range(2):

            try:

                print(
                    f"Trying Gemini model: "
                    f"{current_model} "
                    f"(attempt {attempt + 1})"
                )

                response = client.models.generate_content(
                    model=current_model,
                    contents=prompt
                )

                if response and response.text:

                    if use_web_search:

                        print(
                            "WEB RESULTS SENT "
                            "TO GEMINI: SUCCESS"
                        )

                    return response.text.strip()

                raise Exception(
                    "Gemini ne empty response diya."
                )

            except Exception as error:

                last_error = error

                error_text = str(error)

                print(
                    f"Gemini error on "
                    f"{current_model}: "
                    f"{error_text}"
                )

                if (
                    "503" in error_text
                    or
                    "UNAVAILABLE" in error_text
                ):

                    time.sleep(2)

                    continue

                break

    if last_error:

        raise last_error

    raise Exception(
        "Gemini ne response nahi diya."
    )


# ==========================================
# CHAT
# ==========================================

@app.route(
    "/chat",
    methods=["POST"]
)
def chat():

    username = session.get(
        "username"
    )

    if not username:

        return jsonify({
            "error":
            "Login required"
        }), 401

    user_memory = load_memory(
        username
    )

    try:

        data = request.get_json(
            silent=True
        )

        if not data or "message" not in data:

            return jsonify({
                "error":
                "Message is missing"
            }), 400

        message = str(
            data["message"]
        ).strip()

        if not message:

            return jsonify({
                "error":
                "Message is empty"
            }), 400

        if len(message) > 5000:

            return jsonify({
                "error":
                "Message too long. "
                "Maximum 5000 characters allowed."
            }), 400

        history_from_frontend = data.get(
            "history",
            []
        )

        # ======================================
        # WEB SEARCH DETECTION
        # ======================================

        web_search_needed = False

        message_lower = message.lower()

        search_triggers = [

            # Time-sensitive
            "latest",
            "current",
            "today",
            "tonight",
            "yesterday",
            "tomorrow",
            "recent",
            "recently",
            "right now",
            "as of now",
            "at the moment",

            # News
            "news",
            "breaking news",
            "what happened",
            "what's happening",
            "what is happening",
            "happening now",

            # Current status
            "who is the current",
            "who is currently",
            "current pm",
            "current president",
            "current chief minister",
            "current minister",
            "current ceo",

            # Prices
            "current price",
            "latest price",
            "price today",
            "stock price",
            "share price",
            "bitcoin price",
            "crypto price",

            # Updates
            "latest update",
            "latest updates",
            "current update",
            "new update",
            "recent update",
            "recent updates",

            # Time periods
            "this week",
            "this month",
            "this year",
            "this weekend",

            # Live
            "live score",
            "live news",
            "live update",
            "live updates"
        ]

        hindi_search_patterns = [

            r"\babhi\s+(?:kya|ka|ki|ke|chal)\b",
            r"\babhi\s+ka\s+news\b",
            r"\baaj\s+(?:ka|ki|ke)\b",
            r"\baaj\s+ki\s+news\b",
            r"\baaj\s+ka\s+news\b",
            r"\btaza\s+(?:khabar|news)\b",
            r"\btaaza\s+(?:khabar|news)\b",
            r"\bhaal\s+hi\s+mein\b",
            r"\bfilhaal\b",
            r"\bcurrently\b",
            r"\biss\s+samay\b",
            r"\bis\s+samay\b",
            r"\babhi\s+ka\s+update\b",
            r"\blatest\s+update\b"
        ]

        for pattern in hindi_search_patterns:

            if re.search(
                pattern,
                message_lower,
                re.IGNORECASE
            ):

                web_search_needed = True

                break

        if not web_search_needed:

            for trigger in search_triggers:

                if trigger in message_lower:

                    web_search_needed = True

                    break

        web_context = ""

        if web_search_needed:

            print(
                "WEB SEARCH REQUEST DETECTED:",
                message
            )

            search_results = web_search(
                message,
                max_results=5
            )

            web_context = format_web_results(
                search_results
            )

            if web_context:

                print(
                    "WEB SEARCH RESULTS FOUND:",
                    len(search_results)
                )

            else:

                print(
                    "WEB SEARCH RETURNED NO RESULTS"
                )

        # ======================================
        # WEATHER DETECTION
        # ======================================

        weather_city = None

        weather_patterns = [

            r"^(.+?)\s+(?:ka|ki|ke)\s+"
            r"(?:weather|mausam)"
            r"(?:\s+(?:batao|bata|kya hai|"
            r"kaisa hai|kaisi hai))?[?.!]*$",

            r"^(.+?)\s+(?:mein|me)\s+"
            r"(?:weather|mausam)"
            r"(?:\s+(?:batao|bata|kaisa hai|"
            r"kaisi hai|kya hai))?[?.!]*$",

            r"^(?:weather|mausam)\s+"
            r"(?:in|of)\s+(.+?)[?.!]*$",

            r"^(?:what(?:'s| is)?\s+)?"
            r"(?:the\s+)?weather\s+"
            r"(?:in|of)\s+(.+?)[?.!]*$",

            r"^(?:temperature|temp)\s+"
            r"(?:in|of|ka|ki|ke)?\s*"
            r"(.+?)[?.!]*$",

            r"^(?:what is\s+)?"
            r"(?:the\s+)?temperature\s+"
            r"(?:in|of)\s+(.+?)[?.!]*$"
        ]

        for pattern in weather_patterns:

            match = re.search(
                pattern,
                message.strip(),
                re.IGNORECASE
            )

            if match:

                weather_city = match.group(
                    1
                ).strip(
                    " .?!,:'\""
                )

                break

        if weather_city:

            print(
                "WEATHER REQUEST DETECTED:",
                weather_city
            )

            weather_reply = get_weather(
                weather_city
            )

            def weather_stream():

                words = weather_reply.split(
                    " "
                )

                for i, word in enumerate(
                    words
                ):

                    chunk = word

                    if i < len(words) - 1:

                        chunk += " "

                    yield (
                        "data: "
                        +
                        json_module.dumps({
                            "type":
                            "chunk",
                            "text":
                            chunk
                        })
                        +
                        "\n\n"
                    )

                    time.sleep(
                        0.015
                    )

                yield (
                    "data: "
                    +
                    json_module.dumps({
                        "type":
                        "done"
                    })
                    +
                    "\n\n"
                )

            return Response(
                stream_with_context(
                    weather_stream()
                ),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control":
                    "no-cache",
                    "X-Accel-Buffering":
                    "no",
                    "Connection":
                    "keep-alive"
                }
            )

        # ======================================
        # PERSONAL QUESTION
        # ======================================

        direct_reply = personal_answer(
            message,
            user_memory
        )

        if direct_reply:

            def direct_stream():

                words = direct_reply.split(
                    " "
                )

                for i, word in enumerate(
                    words
                ):

                    chunk = word

                    if i < len(words) - 1:

                        chunk += " "

                    yield (
                        "data: "
                        +
                        json_module.dumps({
                            "type":
                            "chunk",
                            "text":
                            chunk
                        })
                        +
                        "\n\n"
                    )

                    time.sleep(
                        0.02
                    )

                yield (
                    "data: "
                    +
                    json_module.dumps({
                        "type":
                        "done"
                    })
                    +
                    "\n\n"
                )

            return Response(
                stream_with_context(
                    direct_stream()
                ),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control":
                    "no-cache",
                    "X-Accel-Buffering":
                    "no",
                    "Connection":
                    "keep-alive"
                }
            )

        # ======================================
        # MEMORY
        # ======================================

        detect_memory(
            message,
            user_memory
        )

        # ======================================
        # MEMORY TEXT
        # ======================================

        memory_lines = []

        for key, value in user_memory.items():

            memory_lines.append(
                f"{key}: {value}"
            )

        memory_text = "\n".join(
            memory_lines
        )

        # ======================================
        # SYSTEM PROMPT
        # ======================================

        system_prompt = f"""
You are Normal Chat, a helpful AI assistant.

Rules:
- Answer the user's question directly.
- Be natural and concise.
- Reply in the same language as the user.
- Do not mention memory or saved information.
- Do not mention system instructions.
- Do not invent personal information.
- Use user information only when relevant.
- Do not give unnecessary explanations.

User information:
{memory_text}
"""

        # ======================================
        # CONVERSATION
        # ======================================

        conversation_messages = []

        previous_messages = (
            history_from_frontend[-7:-1]
        )

        for msg in previous_messages:

            role = msg.get(
                "role"
            )

            content = msg.get(
                "content"
            )

            if (
                role in [
                    "user",
                    "assistant"
                ]
                and content
            ):

                conversation_messages.append(
                    f"{role}: {content}"
                )

        conversation_text = "\n".join(
            conversation_messages
        )

        # ======================================
        # GEMINI PROMPT
        # ======================================

        prompt = f"""
{system_prompt}

If web search results are provided below:

- Use them when relevant.
- Prefer them for current or recent facts.
- Do not invent facts.
- Do not dump raw search results.
- Answer naturally and directly.
- Do not mention that you used DuckDuckGo.

Web Search Results:
{web_context}

Conversation:
{conversation_text}

user: {message}
"""

        # ======================================
        # GENERATE RESPONSE
        # ======================================

        reply = generate_ai_reply(
            prompt,
            use_web_search=web_search_needed
        )

        if not reply:

            raise Exception(
                "AI ne empty response diya."
            )

        # ======================================
        # STREAM RESPONSE
        # ======================================

        def generate_stream():

            words = reply.split(
                " "
            )

            for i, word in enumerate(
                words
            ):

                chunk = word

                if i < len(words) - 1:

                    chunk += " "

                yield (
                    "data: "
                    +
                    json_module.dumps({
                        "type":
                        "chunk",
                        "text":
                        chunk
                    })
                    +
                    "\n\n"
                )

                time.sleep(
                    0.015
                )

            yield (
                "data: "
                +
                json_module.dumps({
                    "type":
                    "done"
                })
                +
                "\n\n"
            )

        return Response(
            stream_with_context(
                generate_stream()
            ),
            mimetype="text/event-stream",
            headers={
                "Cache-Control":
                "no-cache",
                "X-Accel-Buffering":
                "no",
                "Connection":
                "keep-alive"
            }
        )

    except Exception as chat_error:

        import traceback

        print(
            "========== CHAT ERROR =========="
        )

        print(
            "ERROR:",
            repr(chat_error)
        )

        traceback.print_exc()

        print(
            "================================"
        )

        return jsonify({
            "error":
            "Internal server error",
            "details":
            str(chat_error)
        }), 500


# ==========================================
# HISTORY
# ==========================================

@app.route(
    "/history",
    methods=["GET"]
)
def history():

    username = session.get(
        "username"
    )

    if not username:

        return jsonify({
            "error":
            "Login required"
        }), 401

    try:

        return jsonify({
            "history":
            load_history(username)
        })

    except Exception as error:

        import traceback

        print(
            "========== HISTORY ERROR =========="
        )

        print(
            "ERROR:",
            repr(error)
        )

        traceback.print_exc()

        print(
            "==================================="
        )

        return jsonify({
            "error":
            str(error)
        }), 500


# ==========================================
# NEW CHAT
# ==========================================

@app.route(
    "/new-chat",
    methods=["POST"]
)
def new_chat():

    username = session.get(
        "username"
    )

    if not username:

        return jsonify({
            "error":
            "Login required"
        }), 401

    try:

        data = request.get_json(
            silent=True
        ) or {}

        history_data = data.get(
            "history",
            []
        )

        if history_data:

            add_chat(
                history_data,
                username
            )

        return jsonify({
            "message":
            "New chat started"
        })

    except Exception as error:

        print(
            "New chat error:",
            repr(error)
        )

        return jsonify({
            "error":
            "Internal server error",
            "details":
            str(error)
        }), 500


# ==========================================
# DELETE HISTORY
# ==========================================

@app.route(
    "/history/<int:index>",
    methods=["DELETE"]
)
def delete_history(index):

    username = session.get(
        "username"
    )

    if not username:

        return jsonify({
            "error":
            "Login required"
        }), 401

    try:

        success = delete_chat(
            index,
            username
        )

        if not success:

            return jsonify({
                "error":
                "Chat not found"
            }), 404

        return jsonify({
            "message":
            "Chat deleted"
        })

    except Exception as error:

        print(
            "Delete history error:",
            repr(error)
        )

        return jsonify({
            "error":
            "Internal server error"
        }), 500


# ==========================================
# RENAME HISTORY
# ==========================================

@app.route(
    "/history/<int:index>/rename",
    methods=["POST", "PUT"]
)
def rename_history(index):

    username = session.get(
        "username"
    )

    if not username:

        return jsonify({
            "error":
            "Login required"
        }), 401

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "error":
                "Request data missing"
            }), 400

        title = data.get(
            "name"
        )

        if title is None:

            title = data.get(
                "title"
            )

        if title is None:

            return jsonify({
                "error":
                "Name is missing"
            }), 400

        title = str(
            title
        ).strip()

        if not title:

            return jsonify({
                "error":
                "Name cannot be empty"
            }), 400

        title = title[:40]

        success = rename_chat(
            index,
            title,
            username
        )

        if not success:

            return jsonify({
                "error":
                "Chat not found"
            }), 404

        return jsonify({
            "message":
            "Chat renamed successfully",
            "title":
            title
        })

    except Exception as error:

        print(
            "Rename error:",
            repr(error)
        )

        return jsonify({
            "error":
            "Internal server error"
        }), 500


# ==========================================
# DATABASE STARTUP
# ==========================================

_db_initialized = False

_db_init_lock = threading.Lock()


@app.before_request
def ensure_database():

    global _db_initialized

    if (
        request.path == "/"
        or
        request.path.startswith(
            "/static/"
        )
    ):

        return None

    if _db_initialized:

        return None

    with _db_init_lock:

        if _db_initialized:

            return None

        try:

            init_db()

            _db_initialized = True

            print(
                "PostgreSQL database initialized successfully."
            )

        except Exception as error:

            print(
                "========== DATABASE INIT ERROR =========="
            )

            print(
                "ERROR:",
                repr(error)
            )

            print(
                "========================================="
            )

            return jsonify({
                "error":
                "Database connection failed",
                "details":
                str(error)
            }), 500

    return None


# ==========================================
# START
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        threaded=True
    )