import urllib.parse
import urllib.request
import psycopg2
import json
import re
import os
import threading
import time
import json as json_module
import base64
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

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
from google.genai import types

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

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "..",
    "data"
)

USERS_FILE = os.path.join(
    DATA_DIR,
    "users.json"
)

os.makedirs(
    DATA_DIR,
    exist_ok=True
)


def load_users():

    if not os.path.exists(
        USERS_FILE
    ):
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


app = Flask(
    __name__
)

app.secret_key = SECRET_KEY

app.config[
    "SESSION_COOKIE_HTTPONLY"
] = True

app.config[
    "SESSION_COOKIE_SAMESITE"
] = "Lax"

app.config[
    "SESSION_COOKIE_SECURE"
] = (
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

FALLBACK_MODEL = "gemini-3.5-flash-lite"

client = genai.Client()


# ==========================================
# MEMORY HELPERS
# ==========================================

def clean_value(value):

    value = str(
        value
    ).strip()

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

    text = re.sub(
        r"\s+",
        " ",
        message.strip()
    )

    lower = text.lower()

    lower = lower.replace(
        "favourite",
        "favorite"
    )

    patterns = [

        # NAME

        (
            r"^(?:mera naam|my name is|my name's)"
            r"\s+(.+?)(?:\s+hai)?[.!?]?$",
            "name"
        ),

        (
            r"^(?:main|mai|i am|i'm)"
            r"\s+([A-Za-z][A-Za-z\s]{1,40})[.!?]?$",
            "name"
        ),

        (
            r"^(?:call me|you can call me)"
            r"\s+([A-Za-z][A-Za-z\s]{1,40})[.!?]?$",
            "name"
        ),

        (
            r"^mujhe\s+(.+?)\s+"
            r"(?:ke naam se|naam se)\s+bulao[.!?]?$",
            "name"
        ),

        # COLLEGE

        (
            r"^(?:main|mai)\s+(.+?)\s+me\s+"
            r"padh(?:ta|ti)\s+hoon[.!?]?$",
            "college"
        ),

        (
            r"^(?:i study at|i study in|i go to)"
            r"\s+(.+?)[.!?]?$",
            "college"
        ),

        (
            r"^(?:mera|meri)\s+college\s+"
            r"(.+?)(?:\s+hai)?[.!?]?$",
            "college"
        ),

        # CITY

        (
            r"^(?:main|mai)\s+(.+?)\s+me\s+"
            r"rehta\s+hoon[.!?]?$",
            "city"
        ),

        (
            r"^(?:meri city|my city)\s+"
            r"(.+?)(?:\s+hai)?[.!?]?$",
            "city"
        ),

        (
            r"^(?:i live in|i am from|i'm from)"
            r"\s+(.+?)[.!?]?$",
            "city"
        ),

        # FAVORITE GAME

        (
            r"^(?:mera|meri)\s+favorite\s+game\s+"
            r"(.+?)(?:\s+hai)?[.!?]?$",
            "favorite game"
        ),

        (
            r"^my\s+favorite\s+game\s+is\s+"
            r"(.+?)[.!?]?$",
            "favorite game"
        ),

        (
            r"^(?:mujhe|i)\s+(.+?)\s+"
            r"(?:game\s+)?pasand\s+hai[.!?]?$",
            "favorite game"
        ),

        # FAVORITE COLOR

        (
            r"^(?:mera|meri)\s+favorite\s+color\s+"
            r"(.+?)(?:\s+hai)?[.!?]?$",
            "favorite color"
        ),

        (
            r"^my\s+favorite\s+color\s+is\s+"
            r"(.+?)[.!?]?$",
            "favorite color"
        ),

        # PROGRAMMING LANGUAGE

        (
            r"^(?:mera|meri)\s+favorite\s+"
            r"programming language\s+"
            r"(.+?)(?:\s+hai)?[.!?]?$",
            "favorite programming language"
        ),

        (
            r"^my\s+favorite\s+programming language\s+"
            r"is\s+(.+?)[.!?]?$",
            "favorite programming language"
        ),

        (
            r"^(?:i like|i love)\s+"
            r"(python|java|javascript|c\+\+|c|php|go|rust)"
            r"[.!?]?$",
            "favorite programming language"
        ),

        # GOAL

        (
            r"^mera goal\s+"
            r"(.+?)(?:\s+hai)?[.!?]?$",
            "goal"
        ),

        (
            r"^my goal is\s+"
            r"(.+?)[.!?]?$",
            "goal"
        ),

        (
            r"^(?:i want to become|i want to be|mera aim)"
            r"\s+(.+?)[.!?]?$",
            "goal"
        ),

        # GENERAL PREFERENCE

        (
            r"^mujhe\s+(.+?)\s+"
            r"pasand\s+hai[.!?]?$",
            "preference"
        ),

        (
            r"^i like\s+(.+?)[.!?]?$",
            "preference"
        )
    ]

    for pattern, key in patterns:

        match = re.search(
            pattern,
            lower,
            re.IGNORECASE
        )

        if not match:
            continue

        value = clean_value(
            match.group(1)
        )

        if not value:
            return None, None

        original_match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if original_match:

            value = clean_value(
                original_match.group(1)
            )

        if len(value) > 120:
            return None, None

        if key == "preference":

            save_memory(
                "favorite",
                value,
                user_memory
            )

        else:

            save_memory(
                key,
                value,
                user_memory
            )

        print(
            f"SMART MEMORY DETECTED: {key} = {value}"
        )

        return None, None

    return None, None


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

def _clean_search_url(url):

    url = str(
        url or ""
    ).strip()

    if not url:
        return ""

    try:

        parsed = urllib.parse.urlparse(
            url
        )

        query_params = urllib.parse.parse_qs(
            parsed.query
        )

        google_target = query_params.get(
            "q"
        )

        ddg_target = query_params.get(
            "uddg"
        )

        if (
            google_target
            and google_target[0]
        ):

            url = urllib.parse.unquote(
                google_target[0]
            )

        elif (
            ddg_target
            and ddg_target[0]
        ):

            url = urllib.parse.unquote(
                ddg_target[0]
            )

    except Exception:

        pass

    if url.startswith("/"):
        return ""

    if not url.startswith(
        (
            "http://",
            "https://"
        )
    ):
        return ""

    return url


def _search_domain(url):

    try:

        hostname = urllib.parse.urlparse(
            url
        ).netloc.lower()

        if hostname.startswith(
            "www."
        ):

            hostname = hostname[4:]

        return hostname

    except Exception:

        return ""


def web_search(
    query,
    max_results=5
):

    try:

        query = re.sub(
            r"\s+",
            " ",
            str(query).strip()
        )

        if not query:
            return []

        search_url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=en-IN&gl=IN&ceid=IN:en"
        )

        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent":
                "Mozilla/5.0",
                "Accept":
                "application/rss+xml, application/xml, text/xml, */*"
            }
        )

        with urllib.request.urlopen(
            req,
            timeout=15
        ) as response:

            xml_data = response.read().decode(
                "utf-8",
                errors="ignore"
            )

        root = ET.fromstring(
            xml_data
        )

        results = []

        seen_urls = set()
        seen_titles = set()

        for item in root.findall(
            ".//item"
        ):

            title_element = item.find(
                "title"
            )

            link_element = item.find(
                "link"
            )

            description_element = item.find(
                "description"
            )

            pubdate_element = item.find(
                "pubDate"
            )

            source_element = item.find(
                "source"
            )

            if title_element is None:
                continue

            title = (
                title_element.text or ""
            ).strip()

            url = ""

            if link_element is not None:
                url = (
                    link_element.text or ""
                ).strip()

            snippet = ""

            if description_element is not None:
                snippet = (
                    description_element.text or ""
                ).strip()

            pub_date = ""

            if pubdate_element is not None:
                pub_date = (
                    pubdate_element.text or ""
                ).strip()

            source_name = ""

            if source_element is not None:
                source_name = (
                    source_element.text or ""
                ).strip()

            if not title or not url:
                continue

            # Remove HTML from RSS description.
            snippet = re.sub(
                r"<[^>]+>",
                " ",
                snippet
            )

            snippet = (
                snippet
                .replace(
                    "&nbsp;",
                    " "
                )
            )

            snippet = re.sub(
                r"\s+",
                " ",
                snippet
            ).strip()

            url = _clean_search_url(
                url
            )

            if not url:
                continue

            normalized_url = (
                url.rstrip("/")
                .lower()
            )

            normalized_title = re.sub(
                r"\s+",
                " ",
                title.lower()
            )

            if normalized_url in seen_urls:
                continue

            if normalized_title in seen_titles:
                continue

            seen_urls.add(
                normalized_url
            )

            seen_titles.add(
                normalized_title
            )

            domain = _search_domain(
                url
            )

            source_text = source_name

            if (
                source_element is not None
                and source_element.get("url")
            ):
                source_domain = _search_domain(
                    source_element.get("url")
                )

                if source_domain:
                    domain = source_domain

            if not source_text:
                source_text = domain

            full_snippet = snippet

            if pub_date:
                if full_snippet:
                    full_snippet += (
                        f" | Published: {pub_date}"
                    )
                else:
                    full_snippet = (
                        f"Published: {pub_date}"
                    )

            results.append({
                "title":
                title[:300],

                "url":
                url,

                "domain":
                source_text[:150],

                "snippet":
                full_snippet[:1200]
            })

            if len(results) >= max_results:
                break

        print(
            "WEB SEARCH:",
            query,
            "RESULTS:",
            len(results)
        )

        for index, result in enumerate(
            results,
            start=1
        ):

            print(
                f"  SOURCE {index}: "
                f"{result['domain']} | "
                f"{result['title']}"
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
            f"Source: {result.get('domain', '')}\n"
            f"URL: {result['url']}\n"
            f"{result['snippet']}"
        )

    return "\n\n".join(
        lines
    )


def build_smart_search_query(
    message,
    history
):

    current = re.sub(
        r"\s+",
        " ",
        str(message).strip()
    )

    current = re.sub(
        r"^(please\s+|can you\s+|could you\s+|"
        r"tell me\s+|mujhe\s+|zara\s+|batao\s+)",
        "",
        current,
        flags=re.IGNORECASE
    ).strip()

    context_parts = []

    if isinstance(
        history,
        list
    ):

        for msg in history[-8:]:

            if not isinstance(
                msg,
                dict
            ):
                continue

            role = str(
                msg.get(
                    "role",
                    ""
                )
            ).lower()

            content = str(
                msg.get(
                    "content",
                    ""
                )
            ).strip()

            if (
                role == "user"
                and content
            ):

                context_parts.append(
                    content
                )

    followup = bool(
        re.match(
            r"^(and|also|what about|how about|"
            r"aur|iske|ispe|uska|uske|ye|yeh|"
            r"that|this|same|why|when|where|who|how)\b",
            current,
            re.IGNORECASE
        )
    )

    if (
        followup
        and context_parts
    ):

        query = (
            f"{context_parts[-1]} "
            f"{current}"
        )

    else:

        query = current

    query = re.sub(
        r"\s+",
        " ",
        query
    ).strip()

    return query[:500]


# ==========================================
# GEMINI GENERATION HELPER
# ==========================================

def generate_ai_reply(
    prompt,
    use_web_search=False,
    image_data=None
):

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

                # IMAGE INPUT

                if image_data:

                    image_part = types.Part.from_bytes(
                        data=image_data["bytes"],
                        mime_type=image_data["mime_type"]
                    )

                    contents = [
                        prompt,
                        image_part
                    ]

                    print(
                        "GEMINI IMAGE INPUT: READY",
                        image_data["mime_type"],
                        len(
                            image_data["bytes"]
                        ),
                        "bytes"
                    )

                else:

                    contents = prompt

                # GOOGLE SEARCH GROUNDING

                config = None

                if use_web_search:

                    print(
                        "GEMINI GOOGLE SEARCH: ENABLED"
                    )

                    config = (
                        types.GenerateContentConfig(
                            tools=[
                                types.Tool(
                                    google_search=
                                    types.GoogleSearch()
                                )
                            ]
                        )
                    )

                response = client.models.generate_content(
                    model=current_model,
                    contents=contents,
                    config=config
                )

                if (
                    response
                    and response.text
                ):

                    if use_web_search:

                        grounding = None

                        try:

                            grounding = (
                                response
                                .candidates[0]
                                .grounding_metadata
                                if response.candidates
                                else None
                            )

                        except Exception:

                            grounding = None

                        if grounding:

                            queries = getattr(
                                grounding,
                                "web_search_queries",
                                None
                            ) or []

                            chunks = getattr(
                                grounding,
                                "grounding_chunks",
                                None
                            ) or []

                            print(
                                "GEMINI GOOGLE SEARCH: "
                                "SUCCESS | "
                                f"queries={len(queries)} "
                                f"sources={len(chunks)}"
                            )

                        else:

                            print(
                                "GEMINI GOOGLE SEARCH: "
                                "RESPONSE WITHOUT "
                                "GROUNDING METADATA"
                            )

                    return response.text.strip()

                raise Exception(
                    "Gemini ne empty response diya."
                )

            except Exception as error:

                last_error = error

                error_text = str(
                    error
                )

                print(
                    f"Gemini error on "
                    f"{current_model}: "
                    f"{error_text}"
                )

                # SEARCH QUOTA FALLBACK

                if (
                    use_web_search
                    and "429" in error_text
                ):

                    print(
                        "GEMINI GOOGLE SEARCH: "
                        "QUOTA UNAVAILABLE"
                    )

                    print(
                        "Falling back to "
                        "normal Gemini response..."
                    )

                    try:

                        fallback_response = (
                            client.models.generate_content(
                                model=current_model,
                                contents=contents,
                                config=None
                            )
                        )

                        if (
                            fallback_response
                            and fallback_response.text
                        ):

                            return (
                                fallback_response
                                .text
                                .strip()
                            )

                    except Exception as fallback_error:

                        print(
                            "NORMAL GEMINI "
                            "FALLBACK ERROR:",
                            fallback_error
                        )

                    break

                if (
                    "503" in error_text
                    or
                    "UNAVAILABLE" in error_text
                    or
                    "429" in error_text
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
# IMAGE EDITING
# ==========================================

def is_image_edit_request(
    message
):

    text = re.sub(
        r"\s+",
        " ",
        str(message or "").strip().lower()
    )

    if not text:
        return False

    edit_patterns = [

        r"\b(change|modify|edit|alter|replace|remove|"
        r"add|make|turn|convert|transform)\b.*\b("
        r"background|color|colour|object|person|sky|"
        r"hair|dress|shirt|wall)\b",

        r"\b(background|bg)\s+"
        r"(?:ko|to|into|mein|me)\b",

        r"\b(remove|delete|erase)\b.*\b("
        r"from|image|photo|picture)\b",

        r"\b(add|put|insert)\b.*\b("
        r"to|in|on|the image|the photo|the picture)\b",

        r"\bmake\s+the\s+background\b",

        r"\bbackground\s+("
        r"blue|red|green|black|white|yellow|pink|"
        r"purple|orange|grey|gray)\b",

        r"\b("
        r"blue|red|green|black|white|yellow|pink|"
        r"purple|orange|grey|gray"
        r")\s+background\b",

        r"\bchange\s+.*\bcolor\b",

        r"\bbackground\s+color\b",

        r"\bbackground\s+colour\b"
    ]

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in edit_patterns
    )


def generate_edited_image(
    image_data,
    edit_prompt
):

    if (
        not image_data
        or not image_data.get("bytes")
    ):

        raise ValueError(
            "Image attachment is required "
            "for image editing."
        )

    encoded_image = base64.b64encode(
        image_data["bytes"]
    ).decode(
        "utf-8"
    )

    prompt = (
        "Edit the provided image according to "
        "the user's request. "
        "Preserve the main subject, composition, "
        "proportions, and important details "
        "unless the user explicitly asks to "
        "change them. Make only the requested edit "
        "and keep the result natural and high quality."
        "\n\n"
        f"User request: {edit_prompt}"
    )

    print(
        "IMAGE EDIT REQUEST:",
        edit_prompt
    )

    print(
        "IMAGE EDIT MODEL: "
        "gemini-3.1-flash-image"
    )

    interaction = client.interactions.create(
        model="gemini-3.1-flash-image",
        input=[
            {
                "type":
                "text",
                "text":
                prompt
            },
            {
                "type":
                "image",
                "data":
                encoded_image,
                "mime_type":
                image_data["mime_type"]
            }
        ],
        response_format={
            "type":
            "image",
            "mime_type":
            "image/jpeg"
        }
    )

    output_image = getattr(
        interaction,
        "output_image",
        None
    )

    if (
        output_image is None
        or not getattr(
            output_image,
            "data",
            None
        )
    ):

        raise Exception(
            "Gemini image model ne "
            "edited image return nahi ki."
        )

    output_data = output_image.data

    if isinstance(
        output_data,
        bytes
    ):

        output_data = base64.b64encode(
            output_data
        ).decode(
            "utf-8"
        )

    return {
        "data":
        output_data,

        "mime_type":
        getattr(
            output_image,
            "mime_type",
            None
        ) or "image/png"
    }


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

        if (
            not data
            or "message" not in data
        ):

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

        # ======================================
        # IMAGE ATTACHMENT
        # ======================================

        image_data = None

        image_payload = data.get(
            "image"
        )

        if image_payload:

            if not isinstance(
                image_payload,
                dict
            ):

                return jsonify({
                    "error":
                    "Invalid image attachment"
                }), 400

            mime_type = str(
                image_payload.get(
                    "mimeType",
                    ""
                )
            ).strip().lower()

            data_url = str(
                image_payload.get(
                    "dataUrl",
                    ""
                )
            ).strip()

            if not mime_type.startswith(
                "image/"
            ):

                return jsonify({
                    "error":
                    "Only image attachments "
                    "are supported right now."
                }), 400

            if (
                not data_url.startswith(
                    "data:"
                )
                or
                ";base64," not in data_url
            ):

                return jsonify({
                    "error":
                    "Invalid image data."
                }), 400

            try:

                encoded = data_url.split(
                    ";base64,",
                    1
                )[1]

                image_bytes = base64.b64decode(
                    encoded,
                    validate=True
                )

            except Exception:

                return jsonify({
                    "error":
                    "Image data could not be read."
                }), 400

            if not image_bytes:

                return jsonify({
                    "error":
                    "Image is empty."
                }), 400

            if len(
                image_bytes
            ) > 8 * 1024 * 1024:

                return jsonify({
                    "error":
                    "Image must be smaller "
                    "than 8 MB."
                }), 400

            image_data = {
                "bytes":
                image_bytes,

                "mime_type":
                mime_type
            }

            print(
                "IMAGE ATTACHMENT RECEIVED:",
                image_payload.get(
                    "name",
                    "image"
                ),
                mime_type,
                len(
                    image_bytes
                ),
                "bytes"
            )

        # ======================================
        # IMAGE EDITING
        # ======================================

        if (
            image_data
            and is_image_edit_request(
                message
            )
        ):

            edited_image = generate_edited_image(
                image_data,
                message
            )

            def image_edit_stream():

                yield (
                    "data: "
                    +
                    json_module.dumps({
                        "type":
                        "image",

                        "mimeType":
                        edited_image[
                            "mime_type"
                        ],

                        "data":
                        edited_image[
                            "data"
                        ]
                    })
                    +
                    "\n\n"
                )

                yield (
                    "data: "
                    +
                    json_module.dumps({
                        "type":
                        "chunk",

                        "text":
                        "Image edit complete."
                    })
                    +
                    "\n\n"
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
                    image_edit_stream()
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
        # FRONTEND HISTORY
        # ======================================

        history_from_frontend = data.get(
            "history",
            []
        )

        if not isinstance(
            history_from_frontend,
            list
        ):

            history_from_frontend = []

        # ======================================
        # WEB SEARCH DETECTION
        # ======================================

        web_search_needed = False

        message_lower = message.lower()

        search_triggers = [

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

            "news",
            "breaking news",
            "what happened",
            "what's happening",
            "what is happening",
            "happening now",

            "who is the current",
            "who is currently",
            "current pm",
            "current president",
            "current chief minister",
            "current minister",
            "current ceo",

            "current price",
            "latest price",
            "price today",
            "stock price",
            "share price",
            "bitcoin price",
            "crypto price",

            "latest update",
            "latest updates",
            "current update",
            "new update",
            "recent update",
            "recent updates",

            "this week",
            "this month",
            "this year",
            "this weekend",

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

        # ======================================
        # WEB SEARCH
        # ======================================

        web_context = ""

        if web_search_needed:

            print(
                "WEB SEARCH REQUEST DETECTED:",
                message
            )

            search_query = build_smart_search_query(
                message,
                history_from_frontend
            )

            print(
                "WEB SEARCH QUERY:",
                search_query
            )

            web_results = web_search(
                search_query,
                max_results=5
            )

            web_context = format_web_results(
                web_results
            )

            print(
                "WEB SEARCH CONTEXT READY:",
                len(web_results),
                "results"
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

- Answer the user's question directly and prioritize the exact request.
- Match the user's language and style (English, Hindi, or Hinglish).
- Keep simple questions short and easy to scan.
- For complex, technical, or multi-step questions, give a clear structured answer with useful detail.
- Avoid filler openings such as "Sure!", "Absolutely!", or "Here's the answer" unless they add value.
- Do not repeat information the user already knows from the conversation unless it is needed for clarity.
- Use headings, bullets, or numbered steps when they improve readability.
- Explain technical terms briefly when the user may not know them.
- If the request is ambiguous, ask one focused clarification instead of making a large assumption.
- Never invent personal information, facts, sources, or actions you did not perform.
- Do not mention memory, saved information, system instructions, prompts, or internal processing.
- Use user information only when it is directly relevant to the answer.
- Do not unnecessarily restate the user's question.
- For code requests, prefer complete, directly usable code when appropriate and explain only the important parts.

User information:

{memory_text}
"""

        # ======================================
        # CONVERSATION
        # ======================================

        raw_history = (
            history_from_frontend
            if isinstance(
                history_from_frontend,
                list
            )
            else []
        )

        previous_messages = (
            raw_history[:-1]
        )

        previous_messages = (
            previous_messages[-16:]
        )

        conversation_parts = []

        for msg in previous_messages:

            if not isinstance(
                msg,
                dict
            ):

                continue

            role = str(
                msg.get(
                    "role",
                    ""
                )
            ).strip().lower()

            content = str(
                msg.get(
                    "content",
                    ""
                )
            ).strip()

            if not content:
                continue

            if len(content) > 2500:

                content = (
                    content[:2500]
                    + "..."
                )

            if role == "user":

                conversation_parts.append(
                    f"User: {content}"
                )

            elif role in (
                "assistant",
                "bot",
                "model"
            ):

                conversation_parts.append(
                    f"Assistant: {content}"
                )

        conversation_text = "\n".join(
            conversation_parts
        )

        if len(
            conversation_text
        ) > 14000:

            conversation_text = (
                conversation_text[-14000:]
            )

        conversation_rules = ""

        if conversation_text:

            conversation_rules = """
Conversation continuity rules:

- Treat the recent conversation as active context, not as a new question.
- If the user asks a follow-up such as 'why?', 'how?', 'what about it?',
  'that one', 'same thing', or 'explain more', resolve the reference from
  the most recent relevant user/assistant messages.
- Do not ask the user to repeat information that is already clear from the
  recent conversation.
- If the reference is genuinely ambiguous, ask one short clarification
  question instead of guessing.
- The newest user message always has priority over older context.
"""

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

Web Search Results:

{web_context}

{conversation_rules}

Recent Conversation:

{conversation_text}

Current User Message:

{message}

Image Attachment:

{(
    "An image is attached. Inspect the image and answer the user's request using it."
    if image_data
    else
    "No image is attached."
)}
"""

        # ======================================
        # GENERATE RESPONSE
        # ======================================

        reply = generate_ai_reply(
    prompt,
    use_web_search=(
        web_search_needed
        and not web_context
    ),
    image_data=image_data
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
# BRANCH CONVERSATION
# ==========================================

@app.route(
    "/branch",
    methods=["POST"]
)
def branch_conversation():

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

        if (
            not isinstance(
                history_data,
                list
            )
            or
            not history_data
        ):

            return jsonify({
                "error":
                "Conversation history is required"
            }), 400

        clean_history = []

        for item in history_data[-32:]:

            if not isinstance(
                item,
                dict
            ):

                continue

            role = str(
                item.get(
                    "role",
                    ""
                )
            ).strip().lower()

            content = str(
                item.get(
                    "content",
                    ""
                )
            ).strip()

            if (
                role not in (
                    "user",
                    "assistant"
                )
                or not content
            ):

                continue

            clean_history.append({
                "role":
                role,

                "content":
                content[:5000]
            })

        if not clean_history:

            return jsonify({
                "error":
                "No valid messages to branch"
            }), 400

        add_chat(
            clean_history,
            username
        )

        return jsonify({
            "message":
            "Conversation branch created",

            "history":
            clean_history
        })

    except Exception as error:

        import traceback

        print(
            "========== BRANCH ERROR =========="
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